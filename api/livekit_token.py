"""Vercel serverless function: mints a LiveKit room-join token.

Deployed as /api/livekit_token (not /api/token — that name would shadow
Python's stdlib `token` module, which `tokenize` imports internally). Reads
LIVEKIT_API_KEY / LIVEKIT_API_SECRET / LIVEKIT_URL from Vercel project
environment variables (set these in the Vercel dashboard, not from a .env
file — .env is not deployed).

Uses the raw BaseHTTPRequestHandler pattern on purpose — this is the ONE
approach that's actually been verified working end-to-end on this project.
Two different attempts at a framework-style `app` entrypoint (Flask via a
custom pyproject.toml entrypoint, then FastAPI via a Vercel-recognized
filename) both made the app a catch-all for the entire domain and broke
static file serving at "/" (public/index.html), despite Vercel's docs
claiming static files take precedence. Do not reintroduce an `app`/
`application` variable in this file — Vercel's builder treats any such
variable as a potential single-app entrypoint for the whole project, which
is exactly what broke it twice. A `handler` class here stays scoped to only
this file's own path, /api/livekit_token, and doesn't touch anything else.

Same logic as token_server.py (used for local dev, which does use FastAPI —
that's fine since it's not deployed to Vercel and doesn't share Vercel's
routing rules).
"""

import json
import os
import uuid
from http.server import BaseHTTPRequestHandler

from livekit import api

ROOM_NAME = "kings-hospital-demo"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        identity = f"patient-{uuid.uuid4().hex[:8]}"

        access_token = (
            api.AccessToken(os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"])
            .with_identity(identity)
            .with_name(identity)
            .with_grants(api.VideoGrants(room_join=True, room=ROOM_NAME))
        )

        body = json.dumps(
            {
                "token": access_token.to_jwt(),
                "url": os.environ["LIVEKIT_URL"],
                "room": ROOM_NAME,
                "identity": identity,
            }
        ).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)
