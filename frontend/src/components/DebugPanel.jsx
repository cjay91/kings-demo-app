import { useEffect, useState } from "react";

const STATUS_ENDPOINT = import.meta.env.VITE_STATUS_ENDPOINT;

const STT_OPTIONS = [
  { value: "azure", label: "Azure" },
  { value: "chirp", label: "Google Chirp" },
];
const TTS_OPTIONS = [
  { value: "gemini", label: "Gemini" },
  { value: "azure", label: "Azure" },
  { value: "elevenlabs", label: "ElevenLabs (known bad for Sinhala)" },
];

const STATUS_META = {
  ok: { text: "ready", tone: "ok" },
  quota_exceeded: { text: "quota exceeded", tone: "warn" },
  timeout: { text: "timed out", tone: "error" },
  error: { text: "error", tone: "error" },
  not_configured: { text: "not configured", tone: "error" },
  unknown_provider: { text: "unknown", tone: "error" },
};

function formatRetry(seconds) {
  if (!seconds) return "";
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.round((seconds % 3600) / 60);
  return hrs > 0 ? ` (~${hrs}h${mins}m)` : ` (~${mins}m)`;
}

function StatusBadge({ entry }) {
  if (!entry) return null;
  const meta = STATUS_META[entry.status] ?? STATUS_META.error;
  return (
    <span className={`debug-panel__badge debug-panel__badge--${meta.tone}`} title={entry.detail || ""}>
      {meta.text}
      {entry.status === "quota_exceeded" && formatRetry(entry.retry_after_seconds)}
    </span>
  );
}

/**
 * Hidden (toggle-only) sidebar letting a tester pick STT/TTS provider per
 * call and see a live health check for each, rather than only via
 * STT_PROVIDER/TTS_PROVIDER env vars + a redeploy. Selection only takes
 * effect at the next connect() -- disabled while a call is active since
 * switching mid-call isn't wired up (matches the per-call, not per-turn,
 * granularity agent.py reads this at). Always mounted (not conditionally
 * rendered) so the slide transition has something to animate and the
 * fetched status survives being closed and reopened.
 */
export function DebugPanel({
  isOpen,
  onToggle,
  onClose,
  sttProvider,
  onSttProviderChange,
  ttsProvider,
  onTtsProviderChange,
  disabled,
}) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const checkStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(STATUS_ENDPOINT);
      if (!res.ok) throw new Error(`Status check failed (${res.status})`);
      setStatus(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkStatus();
  }, []);

  return (
    <>
      <div
        className={`debug-sidebar__backdrop ${isOpen ? "debug-sidebar__backdrop--open" : ""}`}
        onClick={onClose}
        aria-hidden="true"
      />
      <button
        type="button"
        className={`debug-sidebar__tab ${isOpen ? "debug-sidebar__tab--open" : ""}`}
        onClick={onToggle}
        aria-label="Toggle provider settings"
      >
        ⚙
      </button>
      <aside className={`debug-sidebar ${isOpen ? "debug-sidebar--open" : ""}`}>
        <div className="debug-sidebar__header">
          <span>Provider settings</span>
          <button type="button" className="debug-sidebar__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <div className="debug-panel">
          <div className="debug-panel__row">
            <label htmlFor="stt-provider">STT</label>
            <select
              id="stt-provider"
              value={sttProvider}
              disabled={disabled}
              onChange={(e) => onSttProviderChange(e.target.value)}
            >
              {STT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <StatusBadge entry={status?.stt?.[sttProvider]} />
          </div>

          <div className="debug-panel__row">
            <label htmlFor="tts-provider">TTS</label>
            <select
              id="tts-provider"
              value={ttsProvider}
              disabled={disabled}
              onChange={(e) => onTtsProviderChange(e.target.value)}
            >
              {TTS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <StatusBadge entry={status?.tts?.[ttsProvider]} />
          </div>

          <button type="button" className="debug-panel__refresh" onClick={checkStatus} disabled={loading}>
            {loading ? "checking..." : "recheck status"}
          </button>
          {error && <p className="debug-panel__error">{error}</p>}
        </div>
      </aside>
    </>
  );
}
