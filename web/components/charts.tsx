"use client";

import { useState } from "react";

import { formatAmount } from "@/lib/profile";

// The charts of "Mis finanzas" and "Perfil 360". Their classes (`legend-row`, `sw`, `bar`,
// `bar-fill`) are styled by each screen's `screen.css`, because the sizes differ per screen.

// Category colours go in this fixed order; anything past the fifth is "other".
const CATEGORY_COLORS = ["var(--q-cat-1)", "var(--q-cat-2)", "var(--q-cat-3)", "var(--q-cat-4)", "var(--q-cat-5)"];
const categoryColor = (i: number) => CATEGORY_COLORS[i] ?? "var(--q-cat-other)";

const MONTH_LABELS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

// A ring sector between two angles (radians), from radius r0 to r1.
function arc(a0: number, a1: number, r0: number, r1: number) {
  const p = (r: number, a: number) => `${(Math.cos(a) * r).toFixed(2)} ${(Math.sin(a) * r).toFixed(2)}`;
  const large = a1 - a0 > Math.PI ? 1 : 0;
  return `M${p(r1, a0)} A${r1} ${r1} 0 ${large} 1 ${p(r1, a1)} L${p(r0, a1)} A${r0} ${r0} 0 ${large} 0 ${p(r0, a0)} Z`;
}

type DonutProps = {
  categories: { name: string; amount: number }[];
  total: number;
  ariaLabel: string;
  // Under the total in the centre, e.g. "MXN".
  unit: string;
  // What a hovered category is a share of: "62% del {shareOf}".
  shareOf: string;
};

// Donut with its legend. Hovering (or focusing) a category grows its arc and shows it in the centre.
export function CategoryDonut({ categories, total, ariaLabel, unit, shareOf }: DonutProps) {
  const [hover, setHover] = useState(-1);
  const off = () => setHover(-1);
  const pct = (amount: number) => `${Math.round((amount / total) * 100)}%`;
  const selected = categories[hover];

  // Each arc starts where the previous one ended, from 12 o'clock.
  const paths: string[] = [];
  let angle = -Math.PI / 2;
  for (const [i, c] of categories.entries()) {
    const end = angle + (c.amount / total) * Math.PI * 2;
    paths.push(arc(angle, end, 64, hover === i ? 98 : 92));
    angle = end;
  }

  return (
    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 24 }}>
      <div style={{ position: "relative", width: 200, height: 200, flex: "0 0 auto" }}>
        <svg width="200" height="200" viewBox="-100 -100 200 200" role="img" aria-label={ariaLabel}>
          {paths.map((d, i) => (
            <path
              key={categories[i].name}
              d={d}
              style={{ fill: categoryColor(i), stroke: "var(--q-ocean)" }}
              strokeWidth="2"
              onMouseEnter={() => setHover(i)}
              onMouseLeave={off}
            />
          ))}
        </svg>
        <div
          style={{
            position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center",
            justifyContent: "center", gap: 2, pointerEvents: "none", textAlign: "center",
          }}
        >
          <span className="q-sub" style={{ maxWidth: 100 }}>{selected ? selected.name : "Total"}</span>
          <span style={{ fontSize: 20, fontWeight: 500, fontVariantNumeric: "tabular-nums" }}>
            {formatAmount(selected ? selected.amount : total)}
          </span>
          <span className="q-sub q-mono">{selected ? `${pct(selected.amount)} del ${shareOf}` : unit}</span>
        </div>
      </div>
      <div style={{ flex: "1 1 220px", display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
        {categories.map((c, i) => (
          <button
            key={c.name}
            type="button"
            className="legend-row"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={off}
            onFocus={() => setHover(i)}
            onBlur={off}
          >
            <span className="sw" style={{ background: categoryColor(i) }} />
            <span>{c.name}</span>
            <span className="q-mono" style={{ color: "var(--q-fog)" }}>{pct(c.amount)}</span>
            <span className="q-mono">{formatAmount(c.amount)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

type BarsProps = {
  monthly: [month: string, amount: number][]; // month is YYYY-MM
  currency: string;
  height: number;
};

// One bar per month over a four-line axis. Hovering (or focusing) a bar dims the rest and shows its amount.
export function MonthlyBars({ monthly, currency, height }: BarsProps) {
  const [hover, setHover] = useState(-1);
  const off = () => setHover(-1);
  // The axis ends at the next multiple of 3,000 so that its three steps are round numbers (6k, 4k, 2k).
  const top = Math.ceil(Math.max(...monthly.map(([, amount]) => amount)) / 3000) * 3000;
  const ticks = [top, (top * 2) / 3, top / 3, 0];

  return (
    <div style={{ position: "relative", height, display: "flex", gap: 8, padding: "0 0 0 44px" }}>
      <div
        style={{
          position: "absolute", left: 0, right: 0, top: 0, bottom: 24, display: "flex", flexDirection: "column",
          justifyContent: "space-between", pointerEvents: "none",
        }}
      >
        {ticks.map((tick) => (
          <div key={tick} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="q-mono q-sub" style={{ width: 36, textAlign: "right", fontSize: 11 }}>
              {tick === 0 ? "0" : `${tick / 1000}k`}
            </span>
            <span style={{ flex: 1, height: 1, background: tick === 0 ? "rgba(230,244,241,.18)" : "rgba(230,244,241,.07)" }} />
          </div>
        ))}
      </div>
      {monthly.map(([month, amount], i) => {
        const label = MONTH_LABELS[Number(month.slice(5)) - 1];
        const h = ((amount / top) * 100).toFixed(1);
        return (
          <button
            key={month}
            type="button"
            className="bar"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={off}
            onFocus={() => setHover(i)}
            onBlur={off}
            aria-label={`${label}: ${formatAmount(amount)} ${currency}`}
          >
            <span style={{ position: "relative", width: "100%", flex: "1 1 auto", display: "flex", alignItems: "flex-end", justifyContent: "center" }}>
              <span className="bar-fill" style={{ height: `${h}%`, opacity: hover === -1 || hover === i ? 1 : 0.45 }} />
              {hover === i && (
                <span
                  style={{
                    position: "absolute", bottom: `calc(${h}% + 8px)`, left: "50%", transform: "translateX(-50%)",
                    whiteSpace: "nowrap", padding: "6px 10px", borderRadius: 8, background: "var(--q-mist)",
                    color: "var(--q-abyss)", fontSize: 12, fontFamily: "var(--q-mono)",
                  }}
                >
                  {formatAmount(amount)} {currency}
                </span>
              )}
            </span>
            <span className="q-sub" style={{ height: 18, fontSize: 12 }}>{label}</span>
          </button>
        );
      })}
    </div>
  );
}
