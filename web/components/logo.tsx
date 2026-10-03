import type { CSSProperties } from "react";

// Quipu's logo: a ring and 12 rays of alternating length, each with a knot. viewBox 0 0 32 32.
function logoPaths() {
  const lines = [], dots = [];
  for (let k = 0; k < 12; k++) {
    const a = (k * 30) * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
    const r2 = k % 2 === 0 ? 14 : 12;
    lines.push(`M${(16 + c * 8.6).toFixed(2)} ${(16 + s * 8.6).toFixed(2)} L${(16 + c * r2).toFixed(2)} ${(16 + s * r2).toFixed(2)}`);
    dots.push(`M${(16 + c * 11).toFixed(2)} ${(16 + s * 11).toFixed(2)} l0 0`);
  }
  return { lines: lines.join(" "), dots: dots.join(" ") };
}

const LOGO = logoPaths();

type IconProps = { size?: number; style?: CSSProperties };

// `animated` moves it at the pace of the nearest `q-st-<state>` container (globals.css).
// `bold` thickens the strokes for the 16-18px sizes.
export function Logo({ size = 28, animated = false, bold = false, style }: IconProps & { animated?: boolean; bold?: boolean }) {
  const ring = <circle cx="16" cy="16" r="5.5" stroke="#E6F4F1" strokeWidth={bold ? 2.6 : 2.2} />;
  const lines = <path d={LOGO.lines} stroke="#2EC4B6" strokeWidth={bold ? 1.8 : 1.5} strokeLinecap="round" />;
  const dots = <path d={LOGO.dots} stroke="#2EC4B6" strokeWidth={bold ? 3.6 : 3.4} strokeLinecap="round" />;
  if (!animated) {
    return (
      <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true" style={{ flex: "0 0 auto", ...style }}>
        {ring}
        {lines}
        {dots}
      </svg>
    );
  }
  return (
    <svg className="q-rot" width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true" style={{ flex: "0 0 auto", overflow: "visible", ...style }}>
      <circle className="q-g q-g-ping" cx="16" cy="16" r="5.5" stroke="#2EC4B6" strokeWidth="0.8" />
      <g className="q-g q-g-lines">{lines}</g>
      <g className="q-g q-g-dots">{dots}</g>
      <g className="q-g q-g-ring">{ring}</g>
    </svg>
  );
}

// Who wrote a message, next to Quipu's logo: the customer...
export function ClientIcon({ size = 24, style }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true" style={{ overflow: "visible", ...style }}>
      <g className="q-p-head">
        <circle cx="16" cy="11.5" r="4.6" stroke="#E6F4F1" strokeWidth="2.2" />
      </g>
      <path d="M7.5 27 C8.6 21 11.8 18.6 16 18.6 C20.2 18.6 23.4 21 24.5 27" stroke="#E6F4F1" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

// ...and a person of the support team, with a headset.
export function AgentIcon({ size = 24, style }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true" style={{ overflow: "visible", ...style }}>
      <g className="q-p-head">
        <circle cx="16" cy="12" r="4.4" stroke="#5DA9E9" strokeWidth="2.2" />
        <path d="M9.6 13 A6.4 6.4 0 0 1 22.4 13" stroke="#5DA9E9" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M9.6 13.6 l0 0 M22.4 13.6 l0 0" stroke="#5DA9E9" strokeWidth="3.4" strokeLinecap="round" />
        <path d="M22.4 15 Q22.4 18.6 18.6 19" stroke="#5DA9E9" strokeWidth="1.3" strokeLinecap="round" />
        <circle className="q-p-mic" cx="18.2" cy="19" r="1.5" fill="#2EC4B6" />
      </g>
      <path d="M7.5 27.5 C8.6 22.5 11.8 20.6 16 20.6 C20.2 20.6 23.4 22.5 24.5 27.5" stroke="#5DA9E9" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}
