import "./App.css";
import { Header } from "./components/Header";
import { CallButton } from "./components/CallButton";
import { StatusPill } from "./components/StatusPill";
import { Transcript } from "./components/Transcript";
import { CallStatus, useVoiceAgent } from "./hooks/useVoiceAgent";

function App() {
  const { status, errorMessage, transcript, activeSpeaker, connect, disconnect } = useVoiceAgent();

  const isIdle = status === CallStatus.IDLE || status === CallStatus.ERROR;

  return (
    <div className="page">
      <Header />

      <main className="hero">
        <p className="hero__eyebrow">සිංහල හඬ සහායක</p>
        <h1 className="hero__title">
          අද ඔබට කුමන ආකාරයෙන්
          <br />
          උදව් කළ හැකිද?
        </h1>
        <p className="hero__subtitle">
          වෛද්‍යවරයෙකු සොයන්න, ලබා ගත හැකි වේලාවන් බලන්න, හෝ පෝලිම් අංකය විමසන්න —
          දුරකථනයෙන් කතා කරන ආකාරයටම, සිංහලෙන්.
        </p>

        <div className="call-panel">
          <CallButton status={status} onConnect={connect} onDisconnect={disconnect} />
          <StatusPill status={status} activeSpeaker={activeSpeaker} errorMessage={errorMessage} />
          {isIdle && <p className="call-panel__hint">ඇමතුම ආරම්භ කිරීමට ඉහත බොත්තම ඔබන්න</p>}
        </div>

        <Transcript messages={transcript} />
      </main>

      <footer className="footer">
        <p>King&rsquo;s Hospital Colombo — නියැදි යාවත්කාලීන කිරීම (Sample Demo)</p>
      </footer>
    </div>
  );
}

export default App;
