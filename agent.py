"""King's Hospital sample voice agent.

Pipeline: Gemini Live API (speech-to-speech, Sinhala) handling STT+LLM+TTS
as a single model, running as a LiveKit Agents worker.

This replaced a Google Cloud STT + Gemini LLM + Google Cloud TTS pipeline
after live testing (with real credentials) found Cloud Text-to-Speech has
zero voices for Sinhala at all -- not a naming issue, the product doesn't
support the language. Cloud STT does work for Sinhala (via the chirp_2
model outside the "global" location), but with TTS a dead end, the whole
pipeline moved to the Gemini Live API instead, authenticated with just
GOOGLE_API_KEY -- no Google Cloud service account needed for this at all.

Sinhala audio quality through Gemini's native-audio model is UNVERIFIED --
confirmed only that it constructs and connects with a Sinhala system
prompt; actual speech quality needs real testing via `python agent.py
console` or a live room. If it's not good enough, see the README's
"Known risks" section for other options that were considered
(Vertex AI Gemini TTS, a third-party Sinhala TTS provider).

Run:
    python agent.py dev      # connects to LiveKit, waits for a room to join
    python agent.py console  # local mic/speaker test, no LiveKit room needed
"""

import os

from dotenv import load_dotenv

from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli
from livekit.plugins.google.realtime import RealtimeModel

import db
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
- හදිසි (emergency) තත්වයක් ඇසෙන්නේ නම් (උදා: හුස්ම ගැනීමේ අපහසුතා, දැඩි
  පපුවේ වේදනාව, සිහිසුන් වීම), වහාම රෝගියාට හදිසි අංශයට හෝ 1990 ට
  සම්බන්ධ වන ලෙස පවසන්න.
- සංවාදය අවසානයේ ස්තුතිය පවසා නිගමනය කරන්න.
"""


class HospitalAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT, tools=HOSPITAL_TOOLS)


async def entrypoint(ctx: JobContext) -> None:
    db.init_db()  # no-op if hospital.db already exists; run seed.py to populate

    await ctx.connect()

    session = AgentSession(
        llm=RealtimeModel(
            api_key=os.environ["GOOGLE_API_KEY"],
            # Not the VertexAI-only "gemini-live-2.5-flash-native-audio" --
            # that model requires vertexai=True and fails fast otherwise.
            model="gemini-2.5-flash-native-audio-preview-12-2025",
            voice="Kore",
            language="si-LK",
        ),
    )

    await session.start(agent=HospitalAgent(), room=ctx.room)
    await session.generate_reply(
        instructions="රෝගියාට සිංහලෙන් උණුසුම්ව ආයුබෝවන් කියා, ඔබට කුමන ආකාරයෙන් "
        "උදව් කළ හැකිද යන්න විමසන්න."
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
