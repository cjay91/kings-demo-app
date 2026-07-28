import { useState } from "react";
import "./App.css";
import { Header } from "./components/Header";
import { CallButton } from "./components/CallButton";
import { StatusPill } from "./components/StatusPill";
import { Transcript } from "./components/Transcript";
import { DebugPanel } from "./components/DebugPanel";
import { CallStatus, useVoiceAgent } from "./hooks/useVoiceAgent";

function App() {
  const {
    status,
    errorMessage,
    transcript,
    activeSpeaker,
    needsAudioUnlock,
    connect,
    disconnect,
    unlockAudio,
  } = useVoiceAgent();

  const [showDebugPanel, setShowDebugPanel] = useState(false);
  const [sttProvider, setSttProvider] = useState("azure");
  const [ttsProvider, setTtsProvider] = useState("gemini");

  const isIdle = status === CallStatus.IDLE || status === CallStatus.ERROR;

  return (
    <div className="page">
      <Header />

      <main className="hero">
        <p className="hero__eyebrow">සිංහල Voice Agent</p>
        <p className="hero__subtitle">
          වෛද්‍යවරයෙකු සොයන්න, ලබා ගත හැකි වේලාවන් බලන්න, හෝ පෝලිම් අංකය විමසන්න
        </p>

        <div className="call-panel">
          <CallButton
            status={status}
            onConnect={() => connect({ sttProvider, ttsProvider })}
            onDisconnect={disconnect}
          />
          <StatusPill status={status} activeSpeaker={activeSpeaker} errorMessage={errorMessage} />
          {isIdle && <p className="call-panel__hint">ඇමතුම ආරම්භ කිරීමට ඉහත බොත්තම ඔබන්න</p>}
          {needsAudioUnlock && (
            <button type="button" className="audio-unlock-btn" onClick={unlockAudio}>
              🔊 හඬ සක්‍රීය කිරීමට ඔබන්න
            </button>
          )}
        </div>

        <DebugPanel
          isOpen={showDebugPanel}
          onToggle={() => setShowDebugPanel((v) => !v)}
          onClose={() => setShowDebugPanel(false)}
          sttProvider={sttProvider}
          onSttProviderChange={setSttProvider}
          ttsProvider={ttsProvider}
          onTtsProviderChange={setTtsProvider}
          disabled={!isIdle}
        />

        <Transcript messages={transcript} />
      </main>

      <footer className="footer">
        <p>King&rsquo;s Hospital Colombo — Sample Demo</p>
      </footer>
    </div>
  );
}

export default App;
