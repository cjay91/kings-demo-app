"""King's Hospital sample voice agent.

Pipeline: streaming cascade, not a single speech-to-speech model:
    mic -> Azure STT (si-LK) -> Gemini LLM (dialog + tool-calling) -> GeminiTTS -> speaker

This replaced two earlier attempts:
1. Google Cloud STT + Gemini LLM + Google Cloud TTS -- dropped after live
   testing found Cloud Text-to-Speech has zero voices for Sinhala at all.
2. Gemini Live API (RealtimeModel, one model for STT+LLM+TTS) -- worked,
   but Sinhala isn't in Gemini Live's supported language list (a live
   session hard-rejects language="si-LK", even bare "si"), and leaving it
   unset to let the model infer the language from the Sinhala system
   prompt caused tool calls to hang indefinitely (Gemini API's own default
   tool_response_scheduling is WHEN_IDLE, and a live duplex session never
   seems to reach "idle").

Current setup, confirmed via live TTS->STT roundtrip testing with real
credentials:
- STT: Azure Speech (si-LK) by default -- accepts the language and
  transcribes real audio, though not perfectly (a synthetic-audio
  roundtrip test produced 2 word-level misses out of ~7 words, including
  one semantic miss -- worth judging against real speech, not just this
  one data point). Set STT_PROVIDER=chirp (or "google") to switch to
  Google Cloud Speech-to-Text's chirp_2 model instead, for side-by-side
  comparison -- confirmed working via live testing, same si-LK caveats
  apply. Needs GOOGLE_SERVICE_ACCOUNT_JSON (see below); Azure doesn't.
- LLM: Gemini 2.5 Flash as a plain text model -- no realtime/audio
  involved here, just normal chat completion + tool-calling.
- TTS: GeminiTTS (livekit.plugins.google.beta), wrapped in a
  tts.FallbackAdapter with "gemini-3.1-flash-tts-preview" (best voice
  quality) as primary and "gemini-2.5-flash-preview-tts" as fallback.
  Both confirmed working via live API calls with just GOOGLE_API_KEY, no
  Vertex AI needed -- a DIFFERENT code path than google.TTS(model_name=...),
  which routes through Vertex AI's Agent Platform API and fails without it
  enabled.

  The fallback exists because "gemini-3.1-flash-tts-preview" has a hard
  cap of 100 requests/DAY on the Gemini API free tier (confirmed via a
  live 429 RESOURCE_EXHAUSTED error) -- ran out from testing, and no
  amount of retrying gets past it; the response said "retry in 20h17m".
  Preview/experimental models seem to get this kind of low fixed quota
  regardless of billing tier, unlike GA models. Quotas are tracked per
  model name, so "gemini-2.5-flash-preview-tts" is a separate (also
  likely capped, but usually less exhausted) bucket -- confirmed the
  FallbackAdapter actually falls through to it live, while the primary
  was mid-quota-exhaustion. If BOTH get exhausted on the same day, that's
  the pattern to expect again, not a new bug -- consider a non-Gemini
  TTS provider (Azure TTS, matching the STT provider) if this keeps
  happening.

GOOGLE_SERVICE_ACCOUNT_JSON holds the Cloud service account key's full
JSON content as a single-line string (not a file path) -- passed straight
to google.STT(credentials_info=...) as a parsed dict. This avoids relying
on a credentials *file* existing inside the deployed container, which
would either need baking the key into the Docker image (a real risk
already hit once with .dockerignore not excluding it by default) or a
secret-file mount; a plain string secret sidesteps both and matches how
every other credential here already works.

Run:
    python agent.py dev      # connects to LiveKit, waits for a room to join
    python agent.py console  # local mic/speaker test, no LiveKit room needed
"""

import json
import os

from dotenv import load_dotenv

from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli
from livekit.agents.tts import FallbackAdapter
from livekit.plugins import azure, google
from livekit.plugins.google.beta import GeminiTTS

import seed
from tools import HOSPITAL_TOOLS

load_dotenv()

SYSTEM_PROMPT = """
ඔබ "King's Hospital Colombo" රෝහලේ දුරකථන හඬ නියෝජිතයෙකි (voice agent).
ඔබේ කාර්යභාරය රෝගීන්ට වෛද්‍යවරුන් සොයා ගැනීමට, ලබා ගත හැකි වේලාවන් පරීක්ෂා කිරීමට,
සහ පෝලිම් අංකය (running number) පිළිබඳ තොරතුරු ලබා දීමට උපකාර කිරීමයි.

මාර්ගෝපදේශ:
- සෑම විටම සිංහලෙන් කෙටියෙන් හා පැහැදිලිව කතා කරන්න.
- වෛද්‍යවරයෙකු, විශේෂඥතාවයක්, හෝ දිනයක් ගැන විමසන විට, සුදුසු මෙවලම
  (tool) එක භාවිතා කර සැබෑ දත්ත පරීක්ෂා කරන්න - කිසි විටෙකත් තොරතුරු
  මවා නොපවසන්න.
- මෙවලමකින් ප්‍රතිඵලයක් නොලැබුනහොත්, එය රෝගියාට විනීතව පවසා විකල්පයක්
  යෝජනා කරන්න (වෙනත් දිනයක් හෝ වෙනත් වෛද්‍යවරයෙකු).
- මෙවලමක ප්‍රතිඵලයේ "approximate name match" (ආසන්න ගැලපීමකි) සඳහන්
  වුවහොත්, එම නම ඔබ අවබෝධ කරගත් ආකාරයටම නිවැරදිදැයි රෝගියාගෙන් තහවුරු
  කරගෙන පමණක් ඉදිරියට යන්න.
- හදිසි (emergency) තත්වයක් ඇසෙන්නේ නම් (උදා: හුස්ම ගැනීමේ අපහසුතා, දැඩි
  පපුවේ වේදනාව, සිහිසුන් වීම), වහාම රෝගියාට හදිසි අංශයට හෝ 1990 ට
  සම්බන්ධ වන ලෙස පවසන්න.
- සංවාදය අවසානයේ ස්තුතිය පවසා නිගමනය කරන්න.
"""

# Fixed opening line, spoken via TTS directly (session.say) rather than a
# generate_reply() LLM round-trip -- lands the greeting immediately instead
# of waiting on a chat completion for a line that's always the same anyway.
GREETING = (
    "ආයුබෝවන්! මම King's Hospital Colombo හි හඬ නියෝජිතයා. "
    "අද ඔබට කුමන ආකාරයෙන් උදව් කළ හැකිද?"
)


class HospitalAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT, tools=HOSPITAL_TOOLS)


def build_stt():
    """STT_PROVIDER=chirp (or "google") switches to Google Cloud
    Speech-to-Text's chirp_2 model; anything else (including unset)
    defaults to Azure. location="us-central1" is required -- chirp
    models aren't available in "global", and chirp_3 (tried first,
    before chirp_2) explicitly rejects si-LK as unsupported."""
    provider = os.environ.get("STT_PROVIDER", "azure").lower()
    if provider in ("chirp", "google"):
        return google.STT(
            languages="si-LK",
            model="chirp_2",
            location="us-central1",
            detect_language=False,
            credentials_info=json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]),
        )
    return azure.STT(
        speech_key=os.environ["AZURE_API_KEY"],
        speech_region=os.environ["AZURE_REGION"],
        language="si-LK",
    )


async def entrypoint(ctx: JobContext) -> None:
    # Re-seed every job rather than relying on hospital.db already being
    # present in the deployed container -- it's git-ignored, and whether a
    # gitignored file survives into a remote build context is exactly the
    # kind of thing that silently doesn't happen (the same category of bug
    # hit earlier with Vercel's Python bundler). Cheap and idempotent
    # (small SQLite dataset), and re-computes session dates relative to
    # "today" each time rather than going stale if the image sits unused.
    seed.run()

    await ctx.connect()

    session = AgentSession(
        stt=build_stt(),
        llm=google.LLM(
            model="gemini-2.5-flash",
            api_key=os.environ["GOOGLE_API_KEY"],
            temperature=0.2,
        ),
        tts=FallbackAdapter(
            [
                GeminiTTS(
                    model="gemini-3.1-flash-tts-preview",
                    voice_name="Kore",
                    api_key=os.environ["GOOGLE_API_KEY"],
                ),
                GeminiTTS(
                    model="gemini-2.5-flash-preview-tts",
                    voice_name="Kore",
                    api_key=os.environ["GOOGLE_API_KEY"],
                ),
            ],
            max_retry_per_tts=1,
        ),
    )

    await session.start(agent=HospitalAgent(), room=ctx.room)
    await session.say(GREETING, allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
