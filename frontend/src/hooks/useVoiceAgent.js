import { useCallback, useRef, useState } from "react";
import { Room, RoomEvent } from "livekit-client";

const TOKEN_ENDPOINT = import.meta.env.VITE_TOKEN_ENDPOINT;
const CLIENT_ID_KEY = "kh_client_id";

// Persisted in sessionStorage (survives a refresh, cleared when the tab
// closes) so reconnecting in the same tab reuses the same LiveKit identity.
// The server then joins under "patient-<this id>" every time -- LiveKit
// disconnects any existing participant with that same identity when a new
// one joins, which is what actually cleans up a stale connection left
// behind by a refresh instead of letting it pile up in the room.
function getClientId() {
  let id = sessionStorage.getItem(CLIENT_ID_KEY);
  if (!id) {
    id = crypto.randomUUID().replace(/-/g, "").slice(0, 16);
    sessionStorage.setItem(CLIENT_ID_KEY, id);
  }
  return id;
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

  const connect = useCallback(async () => {
    setStatus(CallStatus.CONNECTING);
    setErrorMessage(null);
    setTranscript([]);
    setNeedsAudioUnlock(false);

    try {
      const tokenUrl = new URL(TOKEN_ENDPOINT, window.location.origin);
      tokenUrl.searchParams.set("client_id", getClientId());
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

      // A refresh/tab-close only reuses the same LiveKit identity (see
      // getClientId above) if the OLD connection actually leaves the room --
      // otherwise it just sits there until the server times it out on its
      // own. `pagehide` fires reliably for both a refresh and a tab close
      // (unlike `beforeunload`, which browsers increasingly ignore/restrict
      // for bfcache reasons), so send an explicit disconnect there rather
      // than leaving it to a dead socket to eventually get noticed.
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
