import { useEffect, useRef } from "react";

export function Transcript({ messages }) {
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages.length]);

  if (messages.length === 0) {
    return (
      <div className="transcript transcript--empty">
        <p>සංවාදය මෙහි දිස්වේ — කතාබහ ආරම්භ කරන්න.</p>
      </div>
    );
  }

  return (
    <div className="transcript" ref={scrollRef}>
      {messages.map((msg) => (
        <div key={msg.id} className={`transcript__bubble transcript__bubble--${msg.speaker}`}>
          <span className="transcript__label">{msg.speaker === "patient" ? "ඔබ" : "නියෝජිතයා"}</span>
          <p>{msg.text}</p>
        </div>
      ))}
    </div>
  );
}
