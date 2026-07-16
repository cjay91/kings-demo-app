# King's Hospital Voice Bot — Frontend

React + Vite web client for the voice agent. Deploys as its **own separate
Vercel project**, independent of the Python API project in the repo root —
see the main [README](../README.md#deployment) for why (short version:
Vercel's Python runtime treats a FastAPI app as a catch-all for static
files too, so mixing a real React build into that project risks the same
"file silently missing from the deployment" bugs already fought once
today).

## Local dev

```bash
npm install
npm run dev
```

Opens on `http://localhost:5173`. By default (`.env.development`) it calls
`http://localhost:8080/token` — run the root project's `token_server.py`
alongside this for a fully local setup, or just point
`VITE_TOKEN_ENDPOINT` at the deployed API instead.

## Build

```bash
npm run build
```

Outputs to `dist/`.

## Deploying

1. Vercel dashboard → **Add New → Project** → import this same repo again
2. In the import screen, set **Root Directory** to `frontend`
3. Vercel auto-detects Vite — no other config needed
4. `.env.production` already points at the deployed API
   (`VITE_TOKEN_ENDPOINT`) — update it if that API's URL ever changes,
   since Vite bakes env vars in at build time, not read at runtime

## Structure

| Path | Purpose |
|---|---|
| `src/hooks/useVoiceAgent.js` | LiveKit Room lifecycle: token fetch, connect, mic publish, transcript + active-speaker state |
| `src/components/CallButton.jsx` | Big connect/disconnect button, states for idle/connecting/connected |
| `src/components/StatusPill.jsx` | Connection status + who's currently speaking |
| `src/components/Transcript.jsx` | Scrolling conversation view |
| `src/App.jsx` / `src/App.css` | Page layout and all styling |
