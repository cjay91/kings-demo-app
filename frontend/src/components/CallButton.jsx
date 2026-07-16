import { CallStatus } from "../hooks/useVoiceAgent";

const PhoneIcon = () => (
  <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="2">
    <path
      d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const EndCallIcon = () => (
  <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="2">
    <line x1="18" y1="6" x2="6" y2="18" strokeLinecap="round" />
    <line x1="6" y1="6" x2="18" y2="18" strokeLinecap="round" />
  </svg>
);

const Spinner = () => <span className="call-button__spinner" aria-hidden="true" />;

export function CallButton({ status, onConnect, onDisconnect }) {
  const isConnected = status === CallStatus.CONNECTED;
  const isConnecting = status === CallStatus.CONNECTING;

  const handleClick = () => {
    if (isConnected) onDisconnect();
    else if (!isConnecting) onConnect();
  };

  return (
    <div className="call-button-wrap">
      {isConnected && <span className="call-button__ring" aria-hidden="true" />}
      <button
        type="button"
        className={`call-button call-button--${status}`}
        onClick={handleClick}
        disabled={isConnecting}
        aria-label={isConnected ? "Disconnect" : "Connect"}
      >
        {isConnecting ? <Spinner /> : isConnected ? <EndCallIcon /> : <PhoneIcon />}
      </button>
    </div>
  );
}
