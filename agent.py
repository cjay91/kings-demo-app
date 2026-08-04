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

Provider selection (both STT and TTS) can be set two ways:
1. Per-call, from the frontend's hidden debug panel -- sent as
   participant metadata ({"stt_provider": ..., "tts_provider": ...}) on
   the token request (see api/index.py's /api/livekit_token), read back
   out in entrypoint() below via ctx.wait_for_participant(). Lets a
   tester compare providers call-to-call without redeploying or
   touching secrets.
2. STT_PROVIDER / TTS_PROVIDER env vars -- the fallback default when no
   metadata is sent (e.g. token_server.py's local-dev client, which
   doesn't have the debug panel).

Current defaults, confirmed via live TTS->STT roundtrip testing with real
credentials:
- STT: Azure Speech by default, given ["si-LK", "en-US", "ta-IN"] rather
  than a single locked language -- confirmed by reading the plugin's
  source that >1 language switches on Azure's continuous language-ID
  mode, and confirmed live that it matters: locking language="si-LK"
  meant a caller speaking English or Tamil got transcribed as
  confident-sounding Sinhala gibberish (0.60-0.69 confidence, no signal
  anything was wrong), e.g. "I need to see a doctor tomorrow morning" ->
  "අනික ඔබ ක්‍රීඩා කරපු නැටුම් ඕනි". With auto-detect on, the same
  Sinhala/English/Tamil test sentences all came back correctly
  attributed and transcribed. Sinhala-only accuracy itself still isn't
  perfect (a synthetic-audio roundtrip test produced 2 word-level misses
  out of ~7 words -- worth judging against real speech, not just this
  one data point). "chirp" (or "google") switches to Google Cloud
  Speech-to-Text's chirp_2 model instead, Sinhala-only -- confirmed
  working via live testing for si-LK, but does NOT get the same
  multi-language treatment: Google's API rejects multi-language
  recognition together with chirp_2 outright ("Multiple language
  recognition is only available in ... eu, global, us"), and chirp_2
  itself only exists in regional locations like us-central1, not
  eu/global/us -- a genuine platform conflict, confirmed live, not
  worked around here. A head-to-head si-LK-only comparison on the same
  synthetic audio found Chirp dropped a specific detail (an appointment
  time) that Azure preserved, though both got other words wrong -- call
  it a mild edge for Azure, not a clean win. Chirp needs
  GOOGLE_SERVICE_ACCOUNT_JSON (see below); Azure doesn't.
- LLM: Gemini 2.5 Flash as a plain text model -- no realtime/audio
  involved here, just normal chat completion + tool-calling.
- TTS: GeminiTTS (livekit.plugins.google.beta), wrapped in a
  tts.FallbackAdapter with "gemini-3.1-flash-tts-preview" (best voice
  quality) as primary and "gemini-2.5-flash-preview-tts" as fallback.
  Both confirmed working via live API calls with just GOOGLE_API_KEY, no
  Vertex AI needed -- a DIFFERENT code path than google.TTS(model_name=...),
  which routes through Vertex AI's Agent Platform API and fails without it
  enabled.

  Briefly switched primary to Azure TTS (si-LK-ThiliniNeural) after live
  testing found BOTH Gemini TTS models took 8-10 seconds to synthesize
  even the short greeting line -- direct curl timing against the Gemini
  API confirmed this was inherent to the API at the time (matching the
  "high demand" 503s seen earlier), not a one-off, and caused two live
  test calls to end in a CLIENT_INITIATED disconnect ~15s in with no
  error logged, because the caller heard nothing and hung up before the
  slow response arrived. Reverted back to Gemini-primary on request --
  Azure's si-LK voice quality wasn't good enough to justify the latency
  win. If the 8-10s latency reappears in testing, that's the known
  tradeoff being made here, not a new bug -- Azure TTS is the fallback
  to reach for again if it's a dealbreaker.

  The fallback split exists because "gemini-3.1-flash-tts-preview" has a
  hard cap of 100 requests/DAY on the Gemini API free tier (confirmed via
  a live 429 RESOURCE_EXHAUSTED error) -- ran out from testing, and no
  amount of retrying gets past it; the response said "retry in 20h17m".
  Preview/experimental models seem to get this kind of low fixed quota
  regardless of billing tier, unlike GA models. Quotas are tracked per
  model name, so "gemini-2.5-flash-preview-tts" is a separate (also
  likely capped, but usually less exhausted) bucket -- confirmed the
  FallbackAdapter actually falls through to it live, while the primary
  was mid-quota-exhaustion.

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

import asyncio
import json
import os

from dotenv import load_dotenv

from livekit.agents import (
    DEFAULT_API_CONNECT_OPTIONS,
    Agent,
    AgentSession,
    APIConnectionError,
    APIConnectOptions,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.agents import tts as tts_module
from livekit.agents.tts import FallbackAdapter
from livekit.plugins import azure, elevenlabs, google
from livekit.plugins.google.beta import GeminiTTS
from livekit.plugins.google.beta.gemini_tts import ChunkedStream as _GeminiChunkedStream

import seed
from tools import HOSPITAL_TOOLS

load_dotenv()

# Live testing found Gemini TTS occasionally taking 15-40+ seconds with NO error
# raised at all -- reading livekit-agents 1.6.5's ChunkedStream._main_task source
# confirmed conn_options.timeout is accepted but never actually enforced (no
# asyncio.wait_for anywhere around the provider call), so a hung request just hangs
# until the caller gives up and disconnects, and FallbackAdapter never gets a
# retryable error to react to. This wrapper enforces a real per-attempt deadline by
# turning a timeout into a retryable APIConnectionError, which IS something
# FallbackAdapter already knows how to react to (confirmed live: the same warning
# log used for genuine API errors fires for this too).
#
# 12s, not something more aggressive like 5s: direct timed test calls against the
# real API measured successful synthesis of the actual greeting text at 8s, 10s,
# and 16s on different attempts. A shorter timeout would cut off legitimately
# slow-but-working calls on BOTH the primary and secondary Gemini models (they're
# both Gemini, both subject to the same latency), turning "slow" into "always
# fails outright" instead of just "sometimes fails over to the other model".
GEMINI_TTS_ATTEMPT_TIMEOUT_S = 12.0


class _TimeoutBoundChunkedStream(_GeminiChunkedStream):
    async def _run(self, output_emitter) -> None:
        try:
            await asyncio.wait_for(
                super()._run(output_emitter), timeout=GEMINI_TTS_ATTEMPT_TIMEOUT_S
            )
        except asyncio.TimeoutError as e:
            raise APIConnectionError(
                f"gemini tts: synthesis exceeded {GEMINI_TTS_ATTEMPT_TIMEOUT_S}s timeout",
                retryable=True,
            ) from e


class TimeoutBoundGeminiTTS(GeminiTTS):
    def synthesize(
        self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> _TimeoutBoundChunkedStream:
        return _TimeoutBoundChunkedStream(tts=self, input_text=text, conn_options=conn_options)

# Booking confirmation below is scripted, not backed by a real reservation
# tool/DB table -- there's no e-Channelling booking endpoint in this mock
# setup (see tools.py), only search/sessions/availability/running-number.
# Requested behavior: never tell the caller booking isn't possible; instead
# treat it as done and read back patient name, doctor name, date, and phone
# number.
SYSTEM_PROMPT = """
ඔබ "King's Hospital Colombo" රෝහලේ දුරකථන පාරිභෝගික සේවා නියෝජිතවරයෙකි (customer service representative).
ඔබේ කාර්යභාරය රෝගීන්ට වෛද්‍යවරුන් සොයා ගැනීමට, ලබා ගත හැකි වේලාවන් පරීක්ෂා කිරීමට,
සහ පෝලිම් අංකය (running number) පිළිබඳ තොරතුරු ලබා දීමට උපකාර කිරීමයි.

මාර්ගෝපදේශ:
- රෝගියා කතා කරන භාෂාවෙන්ම (සිංහල, ඉංග්‍රීසි, හෝ දෙමළ) කෙටියෙන් හා
  පැහැදිලිව පිළිතුරු දෙන්න. රෝගියා සංවාදය අතරතුර භාෂාව මාරු කළහොත්,
  ඔබත් එයටම මාරු වන්න.
- වෛද්‍යවරයෙකු, විශේෂඥතාවයක්, හෝ දිනයක් ගැන විමසන විට, සුදුසු මෙවලම
  (tool) එක භාවිතා කර සැබෑ දත්ත පරීක්ෂා කරන්න - කිසි විටෙකත් තොරතුරු
  මවා නොපවසන්න.
- මෙවලමකින් ප්‍රතිඵලයක් නොලැබුනහොත්, එය රෝගියාට විනීතව පවසා විකල්පයක්
  යෝජනා කරන්න (වෙනත් දිනයක් හෝ වෙනත් වෛද්‍යවරයෙකු).
- මෙවලමක ප්‍රතිඵලයේ "approximate name match" (ආසන්න ගැලපීමකි) සඳහන්
  වුවහොත්, එම නම ඔබ අවබෝධ කරගත් ආකාරයටම නිවැරදිදැයි රෝගියාගෙන් තහවුරු
  කරගෙන පමණක් ඉදිරියට යන්න.
- රෝගියා වෛද්‍ය සැසියක් වෙන් කර ගැනීමට (booking) ඉල්ලා සිටියහොත්, එය කළ
  නොහැකි බව කිසි විටෙකත් නොපවසන්න. රෝගියාගේ නම සහ සම්බන්ධතා දුරකථන
  අංකය මෙතෙක් නොලැබී ඇත්නම් ඒවා පළමුව විමසන්න. පසුව, වෙන් කිරීම
  සාර්ථකව සිදු කළ බව පවසා, රෝගියාගේ නම, වෛද්‍යවරයාගේ නම, දිනය, සහ
  දුරකථන අංකය නැවත පවසමින් තහවුරු කරන්න.
- හදිසි (emergency) තත්වයක් ඇසෙන්නේ නම් (උදා: හුස්ම ගැනීමේ අපහසුතා, දැඩි
  පපුවේ වේදනාව, සිහිසුන් වීම), වහාම රෝගියාට හදිසි අංශයට හෝ 1990 ට
  සම්බන්ධ වන ලෙස පවසන්න.
- සංවාදය අවසානයේ ස්තුතිය පවසා නිගමනය කරන්න.
"""

# Fixed opening line, spoken via TTS directly (session.say) rather than a
# generate_reply() LLM round-trip -- lands the greeting immediately instead
# of waiting on a chat completion for a line that's always the same anyway.
GREETING = (
    "ආයුබෝවන්! මම King's Hospital Colombo හි පාරිභෝගික සේවා නියෝජිතවරයා. "
    "අද ඔබට කුමන ආකාරයෙන් උදව් කළ හැකිද?"
)


class HospitalAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT, tools=HOSPITAL_TOOLS)


def build_stt(provider: str):
    """provider="chirp" (or "google") switches to Google Cloud
    Speech-to-Text's chirp_2 model; anything else defaults to Azure.
    location="us-central1" is required -- chirp models aren't available
    in "global", and chirp_3 (tried first, before chirp_2) explicitly
    rejects si-LK as unsupported.

    Azure gets a LIST of languages, not a single one -- passing multiple
    candidates to livekit-plugins-azure switches on Azure's continuous
    language-ID mode (confirmed by reading the plugin's source: >1
    language enables auto_detect_source_language_config), which actually
    figures out which language is being spoken per utterance rather than
    forcing every sound into Sinhala phonetics. This was a real, tested
    problem before: locking language="si-LK" meant a caller speaking
    English or Tamil got transcribed as confident-sounding Sinhala
    gibberish with no signal anything was wrong (e.g. "I need to see a
    doctor tomorrow morning" -> "අනික ඔබ ක්‍රීඩා කරපු නැටුම් ඕනි", a
    0.60-confidence non-answer). With auto-detect on, the same three
    sentences (Sinhala/English/Tamil) all came back correctly attributed
    and transcribed in live testing.

    Chirp does NOT get the same treatment -- verified live that it can't:
    Google's API explicitly rejects multi-language recognition together
    with chirp_2 ("Multiple language recognition is only available in
    the following locations: eu, global, us"), and chirp_2 itself only
    exists in regional locations like us-central1, not eu/global/us. A
    genuine platform conflict, not something worth working around here;
    Chirp stays Sinhala-only."""
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
        language=["si-LK", "en-US", "ta-IN"],
    )


def _detect_script(text: str) -> str:
    """Dominant-script detection via plain Unicode ranges -- Sinhala
    (U+0D80-U+0DFF), Tamil (U+0B80-U+0BFF), and Latin/English occupy
    distinct, non-overlapping blocks, so counting characters per range is
    a fast, reliable way to tell them apart without a real language-ID
    library. Only needs to be "good enough" here: it picks which single
    Azure voice speaks a given line, and the LLM only replies in one
    language per turn (see SYSTEM_PROMPT's language-mirroring
    instruction), so a whole utterance is expected to be one script."""
    counts = {"si": 0, "ta": 0, "en": 0}
    for ch in text:
        cp = ord(ch)
        if 0x0D80 <= cp <= 0x0DFF:
            counts["si"] += 1
        elif 0x0B80 <= cp <= 0x0BFF:
            counts["ta"] += 1
        elif ch.isalpha() and cp < 128:
            counts["en"] += 1
    if not any(counts.values()):
        return "si"
    return max(counts, key=counts.get)


class MultilingualAzureTTS(tts_module.TTS):
    """Routes each synthesize() call to a different underlying azure.TTS
    instance based on the dominant script in the text -- lets the agent
    actually speak back in whichever language the caller used. Azure's
    neural voices are each tied to a single locale/persona (confirmed:
    si-LK-ThiliniNeural isn't a general multilingual voice), so there's
    no single instance that can be told "say this in Tamil this time" --
    each language needs its own pre-built azure.TTS, and this class picks
    between them per call instead of the agent being stuck with whichever
    one it was constructed with."""

    def __init__(self, *, speech_key: str, speech_region: str) -> None:
        super().__init__(
            capabilities=tts_module.TTSCapabilities(streaming=False),
            sample_rate=24000,
            num_channels=1,
        )
        self._voices = {
            "si": azure.TTS(
                voice="si-LK-ThiliniNeural",
                language="si-LK",
                speech_key=speech_key,
                speech_region=speech_region,
            ),
            "en": azure.TTS(
                voice="en-US-JennyNeural",
                language="en-US",
                speech_key=speech_key,
                speech_region=speech_region,
            ),
            "ta": azure.TTS(
                voice="ta-IN-PallaviNeural",
                language="ta-IN",
                speech_key=speech_key,
                speech_region=speech_region,
            ),
        }

    def synthesize(
        self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> tts_module.ChunkedStream:
        return self._voices[_detect_script(text)].synthesize(text, conn_options=conn_options)


def build_tts(provider: str):
    """provider="azure" -> MultilingualAzureTTS, which picks between three
    pre-built Azure voices (si-LK/en-US/ta-IN) per response based on the
    detected script -- matches build_stt()'s Azure STT now understanding
    all three languages, so the agent can actually answer back in
    whichever one the caller used, not just transcribe it and then
    respond in Sinhala regardless. Weaker Sinhala voice quality than
    Gemini per live testing, but fast and reliable.

    provider="elevenlabs" -- added as a comparison option for the debug
    panel despite testing badly: ElevenLabs' TTS API rejects an explicit
    si language code on every model (400 unsupported_language), and even
    left to auto-detect, a live roundtrip test (synthesize -> feed back
    through Azure STT) showed it substituting literal English words
    phonetically written in Sinhala script for words it apparently
    couldn't handle -- e.g. "හෘද රෝග" (cardiology) came out as "හාඩ් රොක්"
    ("hard rock"), "සමඟ" (with) as "ස්මිත්" ("Smith"). Kept in as an
    intentionally-bad option so it can be heard/compared directly rather
    than taken on faith; anything else (including unset) defaults to the
    Gemini TTS cascade (better voice quality, but subject to the preview
    models' quota/latency issues -- see TimeoutBoundGeminiTTS above).
    Gemini/ElevenLabs aren't given the same three-way voice routing as
    Azure -- unverified whether they even need it (both claim broader
    multilingual capability by default), and out of scope for now."""
    if provider == "azure":
        return MultilingualAzureTTS(
            speech_key=os.environ["AZURE_API_KEY"],
            speech_region=os.environ["AZURE_REGION"],
        )
    if provider == "elevenlabs":
        return elevenlabs.TTS(
            voice_id="21m00Tcm4TlvDq8ikWAM",  # "Rachel" -- ElevenLabs' default multilingual voice
            model="eleven_multilingual_v2",
            api_key=os.environ["ELEVENLABS_API_KEY"],
        )
    return FallbackAdapter(
        [
            TimeoutBoundGeminiTTS(
                model="gemini-3.1-flash-tts-preview",
                voice_name="Kore",
                api_key=os.environ["GOOGLE_API_KEY"],
            ),
            TimeoutBoundGeminiTTS(
                model="gemini-2.5-flash-preview-tts",
                voice_name="Kore",
                api_key=os.environ["GOOGLE_API_KEY"],
            ),
        ],
        max_retry_per_tts=0,
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

    # Per-call provider selection: the frontend's hidden debug panel sends
    # stt_provider/tts_provider as participant metadata (see
    # api/index.py's /api/livekit_token) rather than baking a single
    # choice into a fixed env var -- lets a tester switch providers
    # per-call from the browser instead of redeploying/updating secrets
    # every time (which is what STT_PROVIDER/TTS_PROVIDER env vars still
    # control as the fallback default, e.g. for the token_server.py local
    # dev client that doesn't send this).
    participant = await ctx.wait_for_participant()
    try:
        metadata = json.loads(participant.metadata) if participant.metadata else {}
    except json.JSONDecodeError:
        metadata = {}
    stt_provider = metadata.get("stt_provider") or os.environ.get("STT_PROVIDER", "azure")
    tts_provider = metadata.get("tts_provider") or os.environ.get("TTS_PROVIDER", "gemini")

    session = AgentSession(
        stt=build_stt(stt_provider.lower()),
        llm=google.LLM(
            model="gemini-2.5-flash",
            api_key=os.environ["GOOGLE_API_KEY"],
            temperature=0.2,
        ),
        tts=build_tts(tts_provider.lower()),
    )

    await session.start(agent=HospitalAgent(), room=ctx.room)
    await session.say(GREETING, allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
