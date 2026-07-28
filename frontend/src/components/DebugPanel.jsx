import { useEffect, useState } from "react";

const STATUS_ENDPOINT = import.meta.env.VITE_STATUS_ENDPOINT;

const STT_OPTIONS = [
  { value: "azure", label: "Azure" },
  { value: "chirp", label: "Google Chirp" },
];
const TTS_OPTIONS = [
  { value: "gemini", label: "Gemini" },
  { value: "azure", label: "Azure" },
  { value: "elevenlabs", label: "ElevenLabs" },
];
// Only one real option right now -- agent.py has no multi-provider LLM
// support, so this row is shown for consistency/visibility but isn't
// actually a live choice (see the disabled select below).
const LLM_OPTIONS = [{ value: "gemini", label: "Gemini" }];

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

function StatusBadge({ entry, provider }) {
  if (!entry) return null;
  // Gemini's real failure modes (503, empty audio/text, an actual socket
  // timeout) all read the same way to a caller -- it just didn't respond in
  // time -- so collapse anything that isn't a clean "ready", "quota
  // exceeded", or "not configured" into "timed out" rather than surfacing
  // the underlying technical distinction here.
  const isGemini = provider === "gemini";
  const collapsedStatus =
    isGemini && !["ok", "quota_exceeded", "not_configured"].includes(entry.status)
      ? "timeout"
      : entry.status;
  const meta = STATUS_META[collapsedStatus] ?? STATUS_META.error;
  return (
    <span className={`debug-panel__badge debug-panel__badge--${meta.tone}`} title={entry.detail || ""}>
      {meta.text}
      {entry.status === "quota_exceeded" && formatRetry(entry.retry_after_seconds)}
    </span>
  );
}

/**
 * Always-visible provider settings card, fixed in a page corner. Lets a
 * tester pick STT/TTS provider per call and see a live health check for
 * each, rather than only via STT_PROVIDER/TTS_PROVIDER env vars + a
 * redeploy. Selection only takes effect at the next connect() -- disabled
 * while a call is active since switching mid-call isn't wired up (matches
 * the per-call, not per-turn, granularity agent.py reads this at).
 */
export function DebugPanel({
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
    <div className="debug-panel">
      <div className="debug-panel__title">Provider settings</div>

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
        <StatusBadge entry={status?.stt?.[sttProvider]} provider={sttProvider} />
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
        <StatusBadge entry={status?.tts?.[ttsProvider]} provider={ttsProvider} />
      </div>

      <div className="debug-panel__row">
        <label htmlFor="llm-provider">LLM</label>
        <select id="llm-provider" value={LLM_OPTIONS[0].value} disabled>
          {LLM_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <StatusBadge entry={status?.llm?.[LLM_OPTIONS[0].value]} provider={LLM_OPTIONS[0].value} />
      </div>

      <button type="button" className="debug-panel__refresh" onClick={checkStatus} disabled={loading}>
        {loading ? "checking..." : "recheck status"}
      </button>
      {error && <p className="debug-panel__error">{error}</p>}
    </div>
  );
}
