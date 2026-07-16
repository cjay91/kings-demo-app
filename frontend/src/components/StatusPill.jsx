import { CallStatus } from "../hooks/useVoiceAgent";

const LABELS = {
  [CallStatus.IDLE]: "සම්බන්ධ වී නැත",
  [CallStatus.CONNECTING]: "සම්බන්ධ වෙමින්...",
  [CallStatus.CONNECTED]: "සම්බන්ධයි — කතා කරන්න",
  [CallStatus.ERROR]: "දෝෂයක් සිදු විය",
};

export function StatusPill({ status, activeSpeaker, errorMessage }) {
  if (status === CallStatus.ERROR) {
    return (
      <div className="status-pill status-pill--error">
        <span className="status-pill__dot" />
        {LABELS[status]}
        {errorMessage && <span className="status-pill__detail">({errorMessage})</span>}
      </div>
    );
  }

  let label = LABELS[status];
  if (status === CallStatus.CONNECTED && activeSpeaker === "agent") {
    label = "නියෝජිතයා කතා කරයි...";
  } else if (status === CallStatus.CONNECTED && activeSpeaker === "patient") {
    label = "ඔබ කතා කරමින්...";
  }

  return (
    <div className={`status-pill status-pill--${status}`}>
      <span className="status-pill__dot" />
      {label}
    </div>
  );
}
