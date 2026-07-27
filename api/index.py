"""Vercel serverless function: the whole backend for this sample app.

Named api/index.py because Vercel's Python runtime only auto-detects an
`app` instance at specific recognized entrypoint filenames — app.py,
index.py, server.py, main.py, wsgi.py, or asgi.py, at the root or inside
src/, app/, or api/.

Per Vercel's docs, deploying a FastAPI app makes it "a single Vercel
Function" — the one function for the whole project. This app therefore
owns every route it needs, including "/", rather than relying on Vercel's
claimed (and, in live testing on this project, unreliable) precedence for
serving public/** separately from a Python function.

INDEX_HTML is embedded directly below as a string literal, NOT read from
public/index.html at runtime. That file is kept for local dev only (see
README) — Vercel's Python bundler only includes files it can trace through
actual Python imports, and a file opened via a plain path string doesn't
qualify, so public/index.html was silently missing from every deployment
that tried to read it that way (confirmed via a live FileNotFoundError at
/var/task/public/index.html, even after configuring vercel.json's
includeFiles to force it in — that didn't help either). Embedding the
content directly in this file's own source removes any dependency on the
bundler's file-inclusion behavior. If you edit the web client, update it in
BOTH public/index.html and INDEX_HTML below.

Reads LIVEKIT_API_KEY / LIVEKIT_API_SECRET / LIVEKIT_URL from Vercel project
environment variables (set in the Vercel dashboard — .env is not deployed).
"""

import json
import os
import re
import uuid

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from livekit import api

import provider_status

CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
STT_PROVIDERS = {"azure", "chirp"}
TTS_PROVIDERS = {"azure", "gemini", "elevenlabs"}

app = FastAPI()

# The React frontend (frontend/) deploys as a separate Vercel project, on a
# different domain, so /api/livekit_token needs to be reachable cross-origin.
# Wide open is fine here -- this endpoint only ever hands out a scoped,
# short-lived room-join token, same as the "no auth" risk already noted in
# the README; there's nothing sensitive to leak by allowing any origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
)

# A shared, hardcoded room name meant every browser tab/tester joined the
# EXACT same room -- so the room never emptied out (and the agent job never
# closed) as long as anyone, anywhere, was connected, and separate testers
# could even end up talking over each other. Each caller now gets their own
# room instead, named from client_id (a fresh id the frontend generates on
# every single connect() call -- NOT persisted across a refresh, see
# useVoiceAgent.js). Reusing the same room name across a refresh was tried
# first and rejected: LiveKit only auto-dispatches an agent the FIRST time a
# room is created, so reconnecting to an already-used room silently got no
# agent at all. A fresh room every time sidesteps that entirely. The agent
# worker has no agent_name/dispatch-rule restriction (see agent.py's
# WorkerOptions), so it accepts a job for any new room automatically --
# nothing else needs to change for this to work.
ROOM_PREFIX = "kings-hospital"

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>King's Hospital Voice Bot — Sample</title>
  <script src="https://cdn.jsdelivr.net/npm/livekit-client/dist/livekit-client.umd.min.js"></script>
  <style>
    body {
      font-family: system-ui, sans-serif;
      max-width: 640px;
      margin: 40px auto;
      padding: 0 16px;
      color: #1a1a1a;
    }
    h1 { font-size: 1.3rem; }
    button {
      font-size: 1rem;
      padding: 10px 20px;
      border-radius: 8px;
      border: none;
      cursor: pointer;
      margin-right: 8px;
    }
    #connectBtn { background: #1a7f37; color: white; }
    #disconnectBtn { background: #b91c1c; color: white; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    #status { margin: 16px 0; font-weight: 600; }
    #transcript {
      border: 1px solid #ddd;
      border-radius: 8px;
      padding: 12px;
      height: 320px;
      overflow-y: auto;
      background: #fafafa;
    }
    .line { margin-bottom: 8px; }
    .patient { color: #0b5cab; }
    .agent { color: #1a7f37; }
  </style>
</head>
<body>
  <h1>King's Hospital Voice Bot — Sample (Sinhala)</h1>
  <p>Click connect, allow microphone access, then speak in Sinhala.</p>

  <button id="connectBtn">Connect</button>
  <button id="disconnectBtn" disabled>Disconnect</button>

  <div id="status">Disconnected</div>
  <div id="transcript"></div>

  <script>
    // Local dev serves this file statically (see README) and runs
    // token_server.py separately on :8080. Once deployed on Vercel, this
    // same file is served from the same origin as /api/livekit_token, so a
    // relative path is used instead.
    const isLocalDev = ["localhost", "127.0.0.1"].includes(window.location.hostname);
    const TOKEN_SERVER_URL = isLocalDev
      ? "http://localhost:8080/token"
      : "/api/livekit_token";

    const connectBtn = document.getElementById("connectBtn");
    const disconnectBtn = document.getElementById("disconnectBtn");
    const statusEl = document.getElementById("status");
    const transcriptEl = document.getElementById("transcript");

    let room = null;

    function addLine(speaker, text) {
      const div = document.createElement("div");
      div.className = "line " + speaker;
      div.textContent = (speaker === "patient" ? "🧑 You: " : "🤖 Agent: ") + text;
      transcriptEl.appendChild(div);
      transcriptEl.scrollTop = transcriptEl.scrollHeight;
    }

    async function connect() {
      connectBtn.disabled = true;
      statusEl.textContent = "Requesting token...";

      const res = await fetch(TOKEN_SERVER_URL);
      const { token, url } = await res.json();

      room = new LivekitClient.Room();

      room.on(LivekitClient.RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === "audio") {
          const el = track.attach();
          document.body.appendChild(el);
        }
      });

      room.on(LivekitClient.RoomEvent.TranscriptionReceived, (segments, participant) => {
        const isPatient = participant?.identity?.startsWith("patient") ?? true;
        for (const seg of segments) {
          if (!seg.final) continue;
          addLine(isPatient ? "patient" : "agent", seg.text);
        }
      });

      room.on(LivekitClient.RoomEvent.Disconnected, () => {
        statusEl.textContent = "Disconnected";
        connectBtn.disabled = false;
        disconnectBtn.disabled = true;
      });

      await room.connect(url, token);
      await room.localParticipant.setMicrophoneEnabled(true);

      statusEl.textContent = "Connected — speak in Sinhala";
      disconnectBtn.disabled = false;
    }

    async function disconnect() {
      if (room) {
        await room.disconnect();
        room = null;
      }
    }

    connectBtn.addEventListener("click", () => connect().catch((e) => {
      statusEl.textContent = "Error: " + e.message;
      connectBtn.disabled = false;
    }));
    disconnectBtn.addEventListener("click", disconnect);
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX_HTML


@app.get("/api/livekit_token")
def get_token(
    client_id: str | None = Query(default=None),
    stt_provider: str | None = Query(default=None),
    tts_provider: str | None = Query(default=None),
):
    # client_id is a fresh id the frontend generates on every connect() call
    # (see useVoiceAgent.js) -- used to derive both the identity and the
    # per-caller room name below. Falls back to a random one if the frontend
    # doesn't send one (older cached frontend build, or a non-browser
    # client) or sends something outside the expected shape.
    if client_id and CLIENT_ID_RE.match(client_id):
        suffix = client_id
    else:
        suffix = uuid.uuid4().hex[:8]

    identity = f"patient-{suffix}"
    room_name = f"{ROOM_PREFIX}-{suffix}"

    # stt_provider/tts_provider come from the frontend's hidden debug panel
    # (see DebugPanel.jsx) -- passed through as participant metadata so
    # agent.py's entrypoint() can pick providers per call instead of only
    # via the STT_PROVIDER/TTS_PROVIDER env vars. Silently ignored (not
    # included in metadata) if outside the known set, so agent.py falls
    # back to its env var default rather than erroring on a bad value.
    metadata = {}
    if stt_provider in STT_PROVIDERS:
        metadata["stt_provider"] = stt_provider
    if tts_provider in TTS_PROVIDERS:
        metadata["tts_provider"] = tts_provider

    access_token = (
        api.AccessToken(os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"])
        .with_identity(identity)
        .with_name(identity)
        .with_grants(api.VideoGrants(room_join=True, room=room_name))
        .with_metadata(json.dumps(metadata))
    )

    return {
        "token": access_token.to_jwt(),
        "url": os.environ["LIVEKIT_URL"],
        "room": room_name,
        "identity": identity,
    }


@app.get("/api/provider_status")
def get_provider_status():
    """Live (best-effort, cached) health check for every STT/TTS provider
    the debug panel can select -- see provider_status.py for exactly what
    each check does and why it's cached the way it is."""
    return {
        "stt": {p: provider_status.check("stt", p) for p in sorted(STT_PROVIDERS)},
        "tts": {p: provider_status.check("tts", p) for p in sorted(TTS_PROVIDERS)},
    }
