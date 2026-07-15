# King's Hospital Voice Bot — Sample App

A minimal working prototype of the voice bot described in the King's Hospital
build guide: a patient talks in **Sinhala**, the agent understands the
request via **Gemini**, looks up doctor availability in a **mock database**
(shaped like the real e-Channelling API), and replies by voice.

This is a sample/demo, not the production system — see "Known risks & what's
mocked" at the bottom before treating it as more than that.

## Architecture

```
Web browser (mic)  →  LiveKit room  →  LiveKit Agent worker (agent.py)
                                          ├─ Gemini Live API (speech-to-speech,
                                          │  si-LK) — STT+LLM+TTS as one model
                                          └─ Tools (tools.py) → SQLite mock DB (db.py)
```

This replaced an earlier Google Cloud STT + Gemini LLM + Google Cloud TTS
pipeline after live testing (with real credentials) found Cloud
Text-to-Speech has zero voices for Sinhala at all — not a naming issue,
the product doesn't support the language. See "Known risks" below.

The 4 tools in `tools.py` map directly to the 4 e-Channelling endpoints in
the build guide (Section 5.1): consultant search, doctor sessions, available
doctors by date, and live running number. Swapping the mock DB for the real
e-Channelling API later means changing `db.py` only — the tool interface
and the agent don't need to change.

## Files

| File | Purpose |
|---|---|
| `db.py` | SQLite schema + query functions (mock e-Channelling DB) |
| `seed.py` | Populates `hospital.db` with sample doctors/sessions |
| `tools.py` | LiveKit function-tools the agent calls to query the DB |
| `agent.py` | The LiveKit Agents worker (Gemini Live API speech-to-speech) — **runs on a persistent host, not Vercel** (see Deployment) |
| `token_server.py` | Local FastAPI + uvicorn server that mints LiveKit room tokens, for local dev only |
| `api/index.py` | FastAPI app deployed to Vercel — serves both `/` and `/api/livekit_token`. The web client HTML is embedded directly in this file as a string (see Deployment for why) |
| `public/index.html` | The same web client HTML, for local dev only (`python -m http.server`). Must be kept in sync with the copy embedded in `api/index.py` if edited |
| `requirements.txt` | Deps shared by `token_server.py` and `api/index.py` (FastAPI, uvicorn, livekit-api, python-dotenv) |
| `agent-requirements.txt` | Full deps for `agent.py` (livekit-agents, Google plugins) |

## Setup

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash; use .venv\Scripts\activate.bat for cmd.exe
pip install -r requirements.txt -r agent-requirements.txt
```

(`requirements.txt` covers both the local token server and the Vercel
function; `agent-requirements.txt` covers the agent worker's much heavier
dependencies, kept separate so Vercel's build never has to touch them — see
Deployment below.)

### 2. Get credentials

- **LiveKit**: create a free project at https://cloud.livekit.io — you need
  the project URL, API key, and API secret. (Self-hosting is also an option;
  point `LIVEKIT_URL` at your own server instead.)
- **Gemini**: get an API key from https://aistudio.google.com/apikey — this
  is the *only* Google credential needed. `agent.py` uses the Gemini Live
  API exclusively (speech-to-speech in one model), authenticated with just
  this key. No Google Cloud service account is required.

Copy `.env.example` to `.env` and fill in all values:

```bash
cp .env.example .env
```

### 3. Seed the mock database

```bash
python seed.py
```

This creates `hospital.db` with 10 sample doctors across 6 specialties and
~14 upcoming sessions.

### 4. Run the agent (quick local test, no browser needed)

```bash
python agent.py console
```

This opens a local mic/speaker test loop directly in your terminal — the
fastest way to judge actual Sinhala speech quality (unverified — see
"Known risks") before wiring up the browser client.

### 5. Run the full stack (browser client)

In three separate terminals:

```bash
# Terminal 1 — the agent worker, waits for a room to join
python agent.py dev

# Terminal 2 — the token server, for the web client to get a room token
python token_server.py

# Terminal 3 — serve the static web client
cd public && python -m http.server 5500
```

Then open http://localhost:5500 in your browser, click **Connect**, allow
microphone access, and speak in Sinhala.

## Example things to try saying

- "මට හෘද රෝග විශේෂඥ වෛද්‍යවරයෙකු ඕන" (I need a cardiologist)
- "හෙට ලබා ගත හැකි වෛද්‍යවරු කවුද?" (Which doctors are available tomorrow?)
- "Dr. Perera ගේ සැසිය කවදද?" (When is Dr. Perera's session?)

## Deployment

Vercel can only host part of this app. Its functions are short-lived
(spin up per request, then shut down) — `agent.py` needs to stay connected
to LiveKit continuously, waiting to be dispatched into rooms, which no
serverless platform (Vercel included) supports. So deployment splits in two:

- **Web client + token endpoint → Vercel** (this repo, as-is)
- **Agent worker → LiveKit Cloud Agents** (a persistent-process host built
  for exactly this)

### Part 1 — Web client + token endpoint on Vercel

`api/index.py` is a FastAPI app and, per Vercel's docs, becomes **the single
Vercel Function for the whole project** — every request funnels through it.
It explicitly defines both routes this app needs: `GET /` and
`GET /api/livekit_token` (mints the room token). `index.py` is one of
Vercel's recognized entrypoint filenames (along with `app.py`, `server.py`,
`main.py`, `wsgi.py`, `asgi.py`), which is why it's not named something more
descriptive — an arbitrary filename isn't auto-detected without extra
config.

This design is the result of three failed attempts, worth understanding
before changing anything here:

1. A Flask app with a custom `pyproject.toml` `[tool.vercel] entrypoint`
   pointing at a non-standard filename — broke `/`, which returned Flask's
   404 page.
2. A FastAPI app at `api/index.py`, but *relying on Vercel's claimed
   static-file precedence* to serve `public/index.html` at `/` without the
   app defining that route itself — broke `/` the same way, returning
   FastAPI's own `{"detail":"Not Found"}`. A bare `BaseHTTPRequestHandler`
   (no `app` at all, hoping to dodge single-function detection entirely)
   also got flagged by Vercel's build-time entrypoint scanner the same way
   `app` was, so that dodge didn't work either. Lesson: don't rely on
   Vercel serving `public/**` separately from a Python function that's
   present in the project — in live testing here, it didn't.
3. `GET /` reading `public/index.html` from disk via a plain file path at
   runtime, with `vercel.json`'s `includeFiles` configured to force it into
   the bundle — still 500'd with `FileNotFoundError` at
   `/var/task/public/index.html`, confirmed via live runtime logs.
   `includeFiles` apparently isn't reliable for this either.

The lesson across all three: don't depend on Vercel's file-inclusion or
routing behavior working the way its docs describe for anything not
reachable through a plain Python import — in live testing here, none of
the documented shortcuts held up. The current version embeds the web
client's HTML directly as a string literal inside `api/index.py` (see
`INDEX_HTML` in that file) — since that file is the entrypoint itself, its
own source is unambiguously always included, no bundler inference
involved. `public/index.html` still exists for local dev only (`python -m
http.server`); if you edit the client, update both copies.
`agent-requirements.txt` stays out of what Vercel installs via
`.vercelignore`, since the agent's dependencies (livekit-agents, Google
plugins) are unrelated and much heavier.

1. Push this repo to GitHub (or GitLab/Bitbucket), then import it in the
   [Vercel dashboard](https://vercel.com/new) — no build settings needed.
2. In **Project Settings → Environment Variables**, add:
   - `LIVEKIT_API_KEY`
   - `LIVEKIT_API_SECRET`
   - `LIVEKIT_URL`
   (Vercel reads these directly — it does not read your local `.env` file,
   which isn't deployed at all.)
3. Deploy. Your client is now live at `https://<your-project>.vercel.app`,
   calling `/api/livekit_token` on the same origin.

If you'd rather deploy from the CLI: `npx vercel` from the repo root, then
`npx vercel env add LIVEKIT_API_KEY` (repeat for the other two) and
`npx vercel --prod`.

### Part 2 — Agent worker on LiveKit Cloud Agents

This needs to run from your own machine/CI since it requires an interactive
browser login to your LiveKit Cloud account — I can't do this step for you.

```bash
# Install the LiveKit CLI, then authenticate
lk cloud auth

# From the repo root — registers the agent and generates a Dockerfile +
# livekit.toml (only if they don't already exist)
lk agent create
```

`lk agent create` will generate a **Dockerfile** using `requirements.txt` by
convention. Since our root `requirements.txt` is the *lightweight* one (for
the token function) and the agent's real dependencies live in
`agent-requirements.txt`, open the generated Dockerfile and change the
`COPY requirements.txt .` / `pip install -r requirements.txt` lines (or the
`uv sync` equivalent, if it picked the uv-based template) to point at
`agent-requirements.txt` instead. Also confirm its `CMD`/`ENTRYPOINT` runs
`agent.py start` (the production, non-dev entrypoint).

Set secrets (these become the container's environment variables) — just
the one Gemini key, no Google Cloud service account needed:

```bash
lk agent update-secrets --secrets "GOOGLE_API_KEY=your_gemini_key"
```

Then deploy and watch it come up:

```bash
lk agent deploy
lk agent status
lk agent logs
```

Once both parts are live, the Vercel-hosted web client creates a LiveKit
room via `/api/livekit_token`, and your LiveKit Cloud-hosted agent worker
picks up that room dispatch automatically — same flow as local dev, just
with both halves running remotely instead of on your machine.

## Known risks & what's mocked

Carried over from the build guide's own risk list (Section 8) — these apply
here too and are the reason this is a sample, not production-ready:

- **Sinhala speech quality through the Gemini Live API is unverified.**
  This project originally used Google Cloud Speech-to-Text + Cloud
  Text-to-Speech for Sinhala, on the assumption both had solid Sinhala
  support. Live testing with real credentials proved that assumption wrong
  for TTS specifically — a `list_voices(language_code="si-LK")` call
  returned **zero voices**; the product doesn't support the language at
  all, not a naming issue. (Cloud STT does accept `si-LK`, but only via the
  `chirp_2` model outside the `location="global"` — `chirp_3` explicitly
  rejects it. That fix is in `agent.py`, but was only confirmed to *accept*
  Sinhala as a language, never quality-tested against real speech.) Given
  TTS was a dead end, the whole pipeline moved to the Gemini Live API
  (`RealtimeModel`, one model for STT+LLM+TTS, authenticated with just
  `GOOGLE_API_KEY`) — confirmed to construct and connect with a Sinhala
  system prompt, but actual audio quality for Sinhala specifically has NOT
  been tested with real speech. Run `python agent.py console` first and
  judge for yourself before building further on top of this — if it's not
  good enough, two other options were identified and not yet tried:
  enabling Vertex AI to use Gemini's TTS models (same 3-piece pipeline
  shape, extra GCP setup), or swapping in a third-party TTS provider with
  documented Sinhala support (e.g. Azure, ElevenLabs) alongside the
  now-working Cloud STT.
- **Database is mocked and static.** No write path, no concurrency handling,
  no real slot-booking — it only supports the 4 read-style lookups.
- **No emergency-call detection or human escalation** — the system prompt
  tells the agent to redirect emergencies verbally, but there's no separate
  safety-critical detection layer like the real system would need (build
  guide Section 2.2, Layer 6).
- **No auth on the token endpoint** — anyone who can reach `/token` (local)
  or `/api/livekit_token` (Vercel) gets a room token. Fine for a demo; would
  need real patient auth before any real deployment.
- **Single hardcoded room** (`kings-hospital-demo`) — every browser session
  joins the same room, so only test with one caller at a time.
