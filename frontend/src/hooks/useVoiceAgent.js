import { useCallback, useRef, useState } from "react";
import { Room, RoomEvent } from "livekit-client";

const TOKEN_ENDPOINT = import.meta.env.VITE_TOKEN_ENDPOINT;

// A fresh id every single connect() call, NOT persisted across a refresh.
// Room name is derived from this on the server (see /api/livekit_token), and
// LiveKit only auto-dispatches an agent to a room the FIRST time it's
// created -- reusing the same room name (e.g. via a sessionStorage-persisted
// id) across a refresh meant the reconnect landed in a room LiveKit didn't
// consider "new", so no agent job ever got dispatched and the caller got
// silence. Since every connect() now gets its own never-reused room, there's
// also no other participant it could ever collide with, so there's no need
// to keep a stable identity around for de-duplication purposes either.
function getClientId() {
  return crypto.randomUUID().replace(/-/g, "").slice(0, 16);
}

export const CallStatus = {
  IDLE: "idle",
  CONNECTING: "connecting",
  CONNECTED: "connected",
  ERROR: "error",
};

/**
 * Owns the LiveKit Room lifecycle: fetching a token, connecting, publishing
 * the mic, attaching the agent's audio track, and surfacing transcript +
 * active-speaker state for the UI to render.
 */
export function useVoiceAgent() {
  const [status, setStatus] = useState(CallStatus.IDLE);
  const [errorMessage, setErrorMessage] = useState(null);
  const [transcript, setTranscript] = useState([]);
  const [activeSpeaker, setActiveSpeaker] = useState(null); // "patient" | "agent" | null
  const [needsAudioUnlock, setNeedsAudioUnlock] = useState(false);

  const roomRef = useRef(null);
  const audioElRef = useRef(null);
  const pageHideHandlerRef = useRef(null);

  const connect = useCallback(async ({ sttProvider, ttsProvider } = {}) => {
    setStatus(CallStatus.CONNECTING);
    setErrorMessage(null);
    setTranscript([]);
    setNeedsAudioUnlock(false);

    try {
      const tokenUrl = new URL(TOKEN_ENDPOINT, window.location.origin);
      tokenUrl.searchParams.set("client_id", getClientId());
      // Optional per-call provider override from the hidden debug panel
      // (see DebugPanel.jsx) -- omitted entirely when not set, so the
      // server falls back to its own env var default.
      if (sttProvider) tokenUrl.searchParams.set("stt_provider", sttProvider);
      if (ttsProvider) tokenUrl.searchParams.set("tts_provider", ttsProvider);
      const res = await fetch(tokenUrl);
      if (!res.ok) throw new Error(`Token request failed (${res.status})`);
      const { token, url } = await res.json();

      const room = new Room();
      roomRef.current = room;

      room.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === "audio") {
          const el = track.attach();
          el.style.display = "none";
          audioElRef.current = el;
          document.body.appendChild(el);
        }
      });

      // Browsers often block autoplay of the agent's audio track until a
      // user gesture unlocks it. LiveKit detects this and flips
      // canPlaybackAudio to false, firing this event -- surface it so the
      // UI can prompt the caller to tap a button (a fresh gesture) that
      // calls room.startAudio() to retry playback.
      room.on(RoomEvent.AudioPlaybackStatusChanged, () => {
        setNeedsAudioUnlock(!room.canPlaybackAudio);
      });

      room.on(RoomEvent.TranscriptionReceived, (segments, participant) => {
        const isPatient = participant?.identity?.startsWith("patient") ?? true;
        const finalSegments = segments.filter((seg) => seg.final);
        if (finalSegments.length === 0) return;

        setTranscript((prev) => [
          ...prev,
          ...finalSegments.map((seg) => ({
            id: seg.id,
            speaker: isPatient ? "patient" : "agent",
            text: seg.text,
          })),
        ]);
      });

      room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
        if (speakers.length === 0) {
          setActiveSpeaker(null);
          return;
        }
        const speaker = speakers[0];
        setActiveSpeaker(speaker.identity?.startsWith("patient") ? "patient" : "agent");
      });

      room.on(RoomEvent.Disconnected, () => {
        if (pageHideHandlerRef.current) {
          window.removeEventListener("pagehide", pageHideHandlerRef.current);
          pageHideHandlerRef.current = null;
        }
        setStatus(CallStatus.IDLE);
        setActiveSpeaker(null);
        roomRef.current = null;
      });

      await room.connect(url, token);
      await room.localParticipant.setMicrophoneEnabled(true);

      // Without this, a refresh/tab-close leaves the OLD connection sitting
      // in its (now-abandoned) room until the server eventually notices the
      // dead socket. `pagehide` fires reliably for both a refresh and a tab
      // close (unlike `beforeunload`, which browsers increasingly
      // ignore/restrict for bfcache reasons), so send an explicit disconnect
      // there instead of waiting on that.
      const handlePageHide = () => {
        room.disconnect();
      };
      window.addEventListener("pagehide", handlePageHide);
      pageHideHandlerRef.current = handlePageHide;

      setStatus(CallStatus.CONNECTED);
      setNeedsAudioUnlock(!room.canPlaybackAudio);
    } catch (err) {
      setStatus(CallStatus.ERROR);
      setErrorMessage(err instanceof Error ? err.message : String(err));
      roomRef.current = null;
    }
  }, []);

  const disconnect = useCallback(async () => {
    if (pageHideHandlerRef.current) {
      window.removeEventListener("pagehide", pageHideHandlerRef.current);
      pageHideHandlerRef.current = null;
    }
    if (roomRef.current) {
      await roomRef.current.disconnect();
      roomRef.current = null;
    }
    if (audioElRef.current) {
      audioElRef.current.remove();
      audioElRef.current = null;
    }
    setStatus(CallStatus.IDLE);
    setActiveSpeaker(null);
    setNeedsAudioUnlock(false);
  }, []);

  const unlockAudio = useCallback(async () => {
    if (roomRef.current) {
      await roomRef.current.startAudio();
      setNeedsAudioUnlock(!roomRef.current.canPlaybackAudio);
    }
  }, []);

  return {
    status,
    errorMessage,
    transcript,
    activeSpeaker,
    needsAudioUnlock,
    connect,
    disconnect,
    unlockAudio,
  };
}
