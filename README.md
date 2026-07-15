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
                                          ├─ STT: Google Cloud Speech (si-LK, chirp_3)
                                          ├─ LLM: Gemini 2.5 Flash (dialog + tool-calling)
                                          ├─ TTS: Google Cloud TTS (si-LK)
                                          └─ Tools (tools.py) → SQLite mock DB (db.py)
```

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
| `agent.py` | The LiveKit Agents worker (STT → LLM → TTS pipeline) — **runs on a persistent host, not Vercel** (see Deployment) |
| `token_server.py` | Local FastAPI + uvicorn server that mints LiveKit room tokens, for local dev only |
| `api/index.py` | Same token logic as a FastAPI app, deployed to Vercel |
| `public/index.html` | Minimal browser client (mic button + live transcript) |
| `requirements.txt` | Lightweight deps for the token server / Vercel function only |
| `agent-requirements.txt` | Full deps for `agent.py` (livekit-agents, Google plugins, Silero) |

## Setup

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash; use .venv\Scripts\activate.bat for cmd.exe
pip install -r requirements.txt -r agent-requirements.txt
```

(`requirements.txt` covers the token server; `agent-requirements.txt` covers
the agent worker. They're kept separate so that deploying the token server
to Vercel later doesn't drag in the agent's heavy dependencies — see
Deployment below. Locally, just install both.)

### 2. Get credentials

- **LiveKit**: create a free project at https://cloud.livekit.io — you need
  the project URL, API key, and API secret. (Self-hosting is also an option;
  point `LIVEKIT_URL` at your own server instead.)
- **Gemini**: get an API key from https://aistudio.google.com/apikey
- **Google Cloud Speech-to-Text + Text-to-Speech**: in a Google Cloud
  project, enable the "Cloud Speech-to-Text API" and "Cloud Text-to-Speech
  API", then create a service account with a role that can call both (e.g.
  "Cloud Speech Administrator" + "Cloud Text-to-Speech Admin", or just
  "Editor" for a quick demo) and download its JSON key.

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
fastest way to sanity-check the Sinhala STT/TTS pipeline before wiring up
the browser client.

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

This repo is already structured for zero-config Vercel deployment:
`public/index.html` is served as the static site, and `api/index.py` — a
FastAPI app — becomes a single Vercel Function serving `/api/livekit_token`.
`index.py` is one of Vercel's recognized entrypoint filenames (along with
`app.py`, `server.py`, `main.py`, `wsgi.py`, `asgi.py`), which is why it's
not named `livekit_token.py` — an arbitrary filename wouldn't be
auto-detected. The root `requirements.txt` — the lightweight one — is what
Vercel installs; `agent-requirements.txt` is listed in `.vercelignore` so
it's never even uploaded.

Per Vercel's docs, requests matching a real file under `public/**` (like
`/` → `public/index.html`) are served by their CDN before ever reaching the
FastAPI app — only unmatched paths, like `/api/livekit_token`, do. This is
the documented, supported pattern, but verify `/` still loads the web
client correctly on your first deploy (ideally a preview deploy) before
relying on it — it's a different code path than a plain per-file function,
and an earlier attempt at this (routing everything through a Flask app via
a custom `pyproject.toml` entrypoint) broke static serving entirely. If `/`
ever 404s again, the fix that's known to work is reverting `api/index.py`
to a plain `BaseHTTPRequestHandler`-based `handler` class (see git history)
scoped only to its own route.

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

Set secrets (these become the container's environment variables):

```bash
lk agent update-secrets --secrets "GOOGLE_API_KEY=your_gemini_key"
lk agent update-secrets --secret-mount ./gcp-service-account.json
lk agent update-secrets --secrets "GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/gcp-service-account.json"
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

- **Sinhala STT/TTS accuracy is unverified.** `chirp_3` was chosen because
  Google's Chirp models have the broadest multilingual coverage, but I
  haven't been able to test actual Sinhala recognition accuracy against real
  speech in this environment (no live Google Cloud credentials here). Test
  this first with `python agent.py console` before building further on top
  of it — if accuracy is poor, that's a hard blocker worth knowing early.
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
