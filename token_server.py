"""Tiny local server that mints LiveKit room-join tokens for the web client.

In a real deployment this would sit behind your normal auth (so only
legitimate patients get a token); for this sample it just hands one out on
request.

Run:
    python token_server.py
Then open public/index.html (it calls http://localhost:8080/token).
"""

import json
import os
import re
import uuid

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from livekit import api

import provider_status

load_dotenv()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
)

LIVEKIT_API_KEY = os.environ["LIVEKIT_API_KEY"]
LIVEKIT_API_SECRET = os.environ["LIVEKIT_API_SECRET"]
LIVEKIT_URL = os.environ["LIVEKIT_URL"]
ROOM_PREFIX = "kings-hospital"
CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
STT_PROVIDERS = {"azure", "chirp"}
TTS_PROVIDERS = {"azure", "gemini", "elevenlabs"}
LLM_PROVIDERS = {"gemini"}


@app.get("/token")
def token(
    client_id: str | None = Query(default=None),
    stt_provider: str | None = Query(default=None),
    tts_provider: str | None = Query(default=None),
):
    # Mirrors api/index.py -- each caller gets their own room (named from a
    # fresh client_id generated on every connect(), not persisted across a
    # refresh -- see useVoiceAgent.js), not one shared hardcoded room, so
    # local dev matches production behavior.
    if client_id and CLIENT_ID_RE.match(client_id):
        suffix = client_id
    else:
        suffix = uuid.uuid4().hex[:8]

    identity = f"patient-{suffix}"
    room_name = f"{ROOM_PREFIX}-{suffix}"

    metadata = {}
    if stt_provider in STT_PROVIDERS:
        metadata["stt_provider"] = stt_provider
    if tts_provider in TTS_PROVIDERS:
        metadata["tts_provider"] = tts_provider

    access_token = (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(api.VideoGrants(room_join=True, room=room_name))
        .with_metadata(json.dumps(metadata))
    )

    return {
        "token": access_token.to_jwt(),
        "url": LIVEKIT_URL,
        "room": room_name,
        "identity": identity,
    }


@app.get("/provider_status")
def get_provider_status():
    return {
        "stt": {p: provider_status.check("stt", p) for p in sorted(STT_PROVIDERS)},
        "tts": {p: provider_status.check("tts", p) for p in sorted(TTS_PROVIDERS)},
        "llm": {p: provider_status.check("llm", p) for p in sorted(LLM_PROVIDERS)},
    }


if __name__ == "__main__":
    port = int(os.environ.get("TOKEN_SERVER_PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
