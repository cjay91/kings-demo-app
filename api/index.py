"""Vercel serverless function: mints a LiveKit room-join token.

Named api/index.py (not api/livekit_token.py) because Vercel's FastAPI
support only auto-detects an `app` instance at specific recognized
entrypoint filenames — app.py, index.py, server.py, main.py, wsgi.py, or
asgi.py, at the root or inside src/, app/, or api/. Per Vercel's docs, this
becomes the single Vercel Function for the whole project; requests that
match an actual file under public/** (like public/index.html at "/") are
served by Vercel's CDN first and never reach this app — only unmatched
paths, like /api/livekit_token, do.

This is a different code path than the previous BaseHTTPRequestHandler
version (which was scoped per-file instead of relying on static-vs-function
precedence) — verify "/" still serves the web client correctly on a preview
deploy before trusting this in production.

Reads LIVEKIT_API_KEY / LIVEKIT_API_SECRET / LIVEKIT_URL from Vercel project
environment variables (set in the Vercel dashboard — .env is not deployed).
"""

import os
import uuid

from fastapi import FastAPI
from livekit import api

app = FastAPI()

ROOM_NAME = "kings-hospital-demo"


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
