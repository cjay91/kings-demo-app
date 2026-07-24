import { useCallback, useRef, useState } from "react";
import { Room, RoomEvent } from "livekit-client";

const TOKEN_ENDPOINT = import.meta.env.VITE_TOKEN_ENDPOINT;

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

  const connect = useCallback(async () => {
    setStatus(CallStatus.CONNECTING);
    setErrorMessage(null);
    setTranscript([]);
    setNeedsAudioUnlock(false);

    try {
      const res = await fetch(TOKEN_ENDPOINT);
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
        setStatus(CallStatus.IDLE);
        setActiveSpeaker(null);
        roomRef.current = null;
      });

      await room.connect(url, token);
      await room.localParticipant.setMicrophoneEnabled(true);

      setStatus(CallStatus.CONNECTED);
      setNeedsAudioUnlock(!room.canPlaybackAudio);
    } catch (err) {
      setStatus(CallStatus.ERROR);
      setErrorMessage(err instanceof Error ? err.message : String(err));
      roomRef.current = null;
    }
  }, []);

  const disconnect = useCallback(async () => {
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
