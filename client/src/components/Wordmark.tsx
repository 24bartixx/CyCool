/**
 * The CoolCycle wordmark (from coolcycle-wordmark.svg), inlined so it uses the Fredoka font loaded in index.html:
 * an SVG shown through <img> can't load web fonts and would fall back to another typeface.
 */
const TYPE = {
  fontFamily: "'Fredoka', ui-rounded, 'Nunito', sans-serif",
  fontWeight: 600,
  fontSize: 150,
  fill: "#042C53",
  letterSpacing: -1,
} as const;

export default function Wordmark({ className }: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 20 740 175" role="img" aria-label="CoolCycle" className={className}>
      <text style={TYPE} x="100" y="140" textAnchor="end">c</text>
      {/* the two "o" letters as bicycle wheels; their bottom edge sits on the text baseline (y=140) */}
      <g transform="translate(104 8)">
        <circle cx="44" cy="91" r="34" fill="none" stroke="#1D9E75" strokeWidth="13" />
        <circle cx="156" cy="91" r="34" fill="none" stroke="#EF9F27" strokeWidth="13" />
        <g fill="none" stroke="#042C53" strokeWidth="9" strokeLinecap="round" strokeLinejoin="round">
          <path d="M44 91 L96 91 L84 54 Z" />
          <path d="M84 54 L140 50 L96 91" />
          <path d="M140 50 L156 91" />
          <path d="M140 50 L144 38 L156 38" />
          <path d="M74 50 L94 50" />
        </g>
      </g>
      <text style={TYPE} x="308" y="140" textAnchor="start">lcycle</text>
    </svg>
  );
}
