const CrossIcon = () => (
  <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
    <path d="M10.5 2.5h3v7h7v3h-7v9h-3v-9h-7v-3h7z" />
  </svg>
);

export function Header() {
  return (
    <header className="header">
      <div className="header__brand">
        <span className="header__crest">
          <CrossIcon />
        </span>
        <span className="header__name">King&rsquo;s Hospital</span>
      </div>
    </header>
  );
}
