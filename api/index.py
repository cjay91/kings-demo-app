"""Vercel serverless function: the whole backend for this sample app.

Named api/index.py because Vercel's Python runtime only auto-detects an
`app` instance at specific recognized entrypoint filenames — app.py,
index.py, server.py, main.py, wsgi.py, or asgi.py, at the root or inside
src/, app/, or api/.

Per Vercel's docs, deploying a FastAPI app makes it "a single Vercel
Function" — the one function for the whole project. Two earlier attempts
relied on Vercel's claimed static-file-takes-precedence behavior to keep
"/" resolving to public/index.html separately from this app, and both
failed in live testing — a bare BaseHTTPRequestHandler also got flagged by
Vercel's entrypoint detection the same way `app` was, so that dodge didn't
work either. Rather than depend on that precedence again, this app serves
"/" itself, reading public/index.html directly — no ambiguity, no reliance
on undocumented routing behavior.

That file isn't reachable via any Python import, so Vercel's bundler didn't
include it in the function's deployment automatically (confirmed via a live
FileNotFoundError at /var/task/public/index.html) — vercel.json's
`functions["api/*.py"].includeFiles` glob forces it in. If that ever stops
working (Vercel bundling behavior has proven inconsistent across attempts
on this project), the error below is written to say exactly what path(s)
were tried, rather than an opaque 500.

Reads LIVEKIT_API_KEY / LIVEKIT_API_SECRET / LIVEKIT_URL from Vercel project
environment variables (set in the Vercel dashboard — .env is not deployed).
"""

import os
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from livekit import api

app = FastAPI()

ROOM_NAME = "kings-hospital-demo"

CANDIDATE_INDEX_HTML_PATHS = [
    Path(__file__).resolve().parent.parent / "public" / "index.html",
    Path("public/index.html"),  # relative to cwd, in case __file__-relative differs
]


@app.get("/", response_class=HTMLResponse)
def index():
    for path in CANDIDATE_INDEX_HTML_PATHS:
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            continue

    tried = ", ".join(str(p) for p in CANDIDATE_INDEX_HTML_PATHS)
    return HTMLResponse(
        f"<pre>public/index.html not found. Tried: {tried}</pre>", status_code=500
    )


@app.get("/api/livekit_token")
def get_token():
    identity = f"patient-{uuid.uuid4().hex[:8]}"

    access_token = (
        api.AccessToken(os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"])
        .with_identity(identity)
        .with_name(identity)
        .with_grants(api.VideoGrants(room_join=True, room=ROOM_NAME))
    )

    return {
        "token": access_token.to_jwt(),
        "url": os.environ["LIVEKIT_URL"],
        "room": ROOM_NAME,
        "identity": identity,
    }
