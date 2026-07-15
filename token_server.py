"""Tiny local server that mints LiveKit room-join tokens for the web client.

In a real deployment this would sit behind your normal auth (so only
legitimate patients get a token); for this sample it just hands one out on
request.

Run:
    python token_server.py
Then open public/index.html (it calls http://localhost:8080/token).
"""

import os
import uuid

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from livekit import api

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
ROOM_NAME = "kings-hospital-demo"


@app.get("/token")
def token():
    identity = f"patient-{uuid.uuid4().hex[:8]}"

    access_token = (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(api.VideoGrants(room_join=True, room=ROOM_NAME))
    )

    return {
        "token": access_token.to_jwt(),
        "url": LIVEKIT_URL,
        "room": ROOM_NAME,
        "identity": identity,
    }


if __name__ == "__main__":
    port = int(os.environ.get("TOKEN_SERVER_PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
