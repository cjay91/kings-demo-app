"""Lightweight, best-effort live health checks for each STT/TTS provider.

Used by /api/provider_status (see api/index.py, token_server.py), which the
frontend's hidden debug panel calls so a tester can see whether a provider is
likely to work *before* starting a call -- particularly relevant for Gemini
TTS's 100-requests/day quota, which has been silently exhausted more than
once during testing with no warning otherwise until a real call failed.

Caching is a plain in-memory dict, NOT reliable across cold starts when this
runs as a Vercel serverless function -- accepted as a demo-appropriate
tradeoff rather than standing up real shared storage just for a status
check. Checking Gemini's quota costs one real request against the same
100/day cap it's reporting on, so that check is cached aggressively, and
once exhausted, cached for exactly as long as Google's own error says to
wait before retrying.
"""

import json
import os
import time
import urllib.error
import urllib.request

_cache: dict[str, tuple[float, dict]] = {}


def _cached(key: str, ttl_seconds: float, compute_fn) -> dict:
    now = time.time()
    if key in _cache and _cache[key][0] > now:
        return _cache[key][1]
    result = compute_fn()
    ttl = result.pop("_cache_seconds", ttl_seconds)
    _cache[key] = (now + ttl, result)
    return result


def check_azure_tts() -> dict:
    def compute():
        region = os.environ.get("AZURE_REGION")
        key = os.environ.get("AZURE_API_KEY")
        if not region or not key:
            return {"status": "not_configured"}
        req = urllib.request.Request(
            f"https://{region}.tts.speech.microsoft.com/cognitiveservices/voices/list",
            headers={"Ocp-Apim-Subscription-Key": key},
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                return {"status": "ok" if resp.status == 200 else "error"}
        except urllib.error.HTTPError as e:
            return {"status": "error", "detail": f"HTTP {e.code}"}
        except Exception as e:
            return {"status": "error", "detail": str(e)}

    return _cached("azure_tts", 30, compute)


def check_azure_stt() -> dict:
    def compute():
        region = os.environ.get("AZURE_REGION")
        key = os.environ.get("AZURE_API_KEY")
        if not region or not key:
            return {"status": "not_configured"}
        req = urllib.request.Request(
            f"https://{region}.api.cognitive.microsoft.com/sts/v1.0/issueToken",
            data=b"",
            headers={"Ocp-Apim-Subscription-Key": key, "Content-Length": "0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                return {"status": "ok" if resp.status == 200 else "error"}
        except urllib.error.HTTPError as e:
            return {"status": "error", "detail": f"HTTP {e.code}"}
        except Exception as e:
            return {"status": "error", "detail": str(e)}

    return _cached("azure_stt", 30, compute)


def check_chirp_stt() -> dict:
    def compute():
        raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not raw:
            return {"status": "not_configured"}
        try:
            import google.auth.transport.requests as gar
            from google.oauth2 import service_account

            info = json.loads(raw)
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            creds.refresh(gar.Request())
            return {"status": "ok"}
        except Exception as e:
            # Confirms auth only, not the speech.recognizers.recognize IAM
            # permission specifically (that needs an actual recognize call,
            # which has a real cost) -- still catches the class of failure
            # already hit once (a valid-looking key with no API access).
            return {"status": "error", "detail": str(e)[:200]}

    return _cached("chirp_stt", 60, compute)


def check_gemini_tts() -> dict:
    def compute():
        key = os.environ.get("GOOGLE_API_KEY")
        if not key:
            return {"status": "not_configured"}
        body = json.dumps(
            {
                "contents": [{"parts": [{"text": "hi"}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}
                    },
                },
            }
        ).encode()
        req = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-3.1-flash-tts-preview:generateContent?key={key}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15):
                return {"status": "ok", "_cache_seconds": 300}
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            if e.code == 429:
                retry_seconds = 3600
                try:
                    parsed = json.loads(detail)
                    for d in parsed.get("error", {}).get("details", []):
                        if "retryDelay" in d:
                            retry_seconds = int(str(d["retryDelay"]).rstrip("s"))
                except Exception:
                    pass
                return {
                    "status": "quota_exceeded",
                    "retry_after_seconds": retry_seconds,
                    "_cache_seconds": retry_seconds,
                }
            return {"status": "error", "detail": f"HTTP {e.code}", "_cache_seconds": 30}
        except Exception as e:
            return {"status": "error", "detail": str(e), "_cache_seconds": 30}

    return _cached("gemini_tts", 300, compute)


_CHECKS = {
    ("stt", "azure"): check_azure_stt,
    ("stt", "chirp"): check_chirp_stt,
    ("tts", "azure"): check_azure_tts,
    ("tts", "gemini"): check_gemini_tts,
}


def check(kind: str, provider: str) -> dict:
    fn = _CHECKS.get((kind, provider))
    if not fn:
        return {"status": "unknown_provider"}
    return fn()
