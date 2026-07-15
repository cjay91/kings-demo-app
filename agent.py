"""King's Hospital sample voice agent.

Pipeline: Google Cloud STT (Sinhala) -> Gemini (dialog + tool-calling) ->
Google Cloud TTS (Sinhala), running as a LiveKit Agents worker.

Run:
    python agent.py dev      # connects to LiveKit, waits for a room to join
    python agent.py console  # local mic/speaker test, no LiveKit room needed
"""

from dotenv import load_dotenv

from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli
from livekit.plugins import google, silero

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
        # chirp_3 has the broadest multilingual coverage of Google's STT
        # models, which matters most for a lower-resource language like
        # Sinhala. Verify accuracy against real call samples before relying
        # on this for anything beyond a demo (see README "Known risks").
        stt=google.STT(languages="si-LK", model="chirp_3", detect_language=False),
        llm=google.LLM(model="gemini-2.5-flash", temperature=0.2),
        tts=google.TTS(language="si-LK", voice_name="si-LK-Standard-A"),
        vad=silero.VAD.load(),
    )

    await session.start(agent=HospitalAgent(), room=ctx.room)
    await session.generate_reply(
        instructions="රෝගියාට සිංහලෙන් උණුසුම්ව ආයුබෝවන් කියා, ඔබට කුමන ආකාරයෙන් "
        "උදව් කළ හැකිද යන්න විමසන්න."
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
