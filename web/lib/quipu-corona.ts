// Quipu's large avatar: a khipu that curls into a crown. Taken from the design handoff
// (quipu-corona.js, version C, slight bounce); the math and the parameters are the designer's and
// are not to be tuned here. It draws inside an <svg viewBox="-100 -100 200 200">.

export type CoronaMode = "idle" | "listening" | "thinking" | "speaking";

const COLORS = ["#2EC4B6", "#E6F4F1", "#5DA9E9", "#1B998B"];
const RING_LIGHT = "#E6F4F1";
const RING_DASH = "#2EC4B6";

const TARGETS: Record<CoronaMode, number> = { idle: 0, listening: 0.42, thinking: 1, speaking: 1 };
// main cords: index → [position on the stretched khipu (0..1), stretched length]
const MAINS: Record<number, [number, number]> = {
  1: [0.22, 58], 4: [0.33, 84], 6: [0.44, 66], 9: [0.56, 92], 11: [0.67, 54], 14: [0.78, 74],
};
const EXTRAS_ORDER = [7, 8, 5, 10, 3, 12, 2, 13, 0, 15]; // the order the other cords sprout in
const VALUES = [921, 312, 312, 673, 473, 268, 145, 730, 512, 881, 406, 239, 654, 357, 128, 790];

const N = 16;
const R = 30; // radius of the closed crown
const L_SHORT = 30; // length of a cord on the crown
const STRETCH_LEN = 112;
const SPRING_W = 8; // stiffness (~0.8 s)
const SPRING_Z = 0.7; // damping (<1: slight bounce)

const NS = "http://www.w3.org/2000/svg";

export function createCorona(svg: SVGSVGElement) {
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const rank: Record<number, number> = {};
  EXTRAS_ORDER.forEach((i, r) => { rank[i] = r; });
  const knotDist = VALUES.map((v) => {
    const H = Math.floor(v / 100), T = Math.floor(v / 10) % 10, d = [7];
    if (H >= 2) d.push(13);
    if (T >= 1) d.push(24);
    return d;
  });

  const mk = (attrs: Record<string, string | number>) => {
    const p = document.createElementNS(NS, "path");
    for (const k in attrs) p.setAttribute(k, String(attrs[k]));
    p.setAttribute("fill", "none");
    svg.appendChild(p);
    return p;
  };
  const lines = COLORS.map((c) => mk({ stroke: c, "stroke-width": 2.2, "stroke-linecap": "round" }));
  const knots = COLORS.map((c) => mk({ stroke: c, "stroke-width": 6.5, "stroke-linecap": "round" }));
  const ringA = mk({ stroke: RING_LIGHT, "stroke-width": 5.5, "stroke-linecap": "round", "stroke-linejoin": "round" });
  const ringB = mk({ stroke: RING_DASH, "stroke-width": 5.5, "stroke-dasharray": "2 4" });

  let mode: CoronaMode = "idle";
  let x = TARGETS[mode], v = 0; // the spring
  let sp = 0; // smooth mix of "speaking"
  let th = 0; // smooth mix of "thinking"
  let level: number | null = null; // loudness of the voice, when the page knows it
  let tau = 0, raf = 0, last: number | null = null;

  function draw() {
    const TAU = Math.PI * 2;
    const tc = Math.max(0, Math.min(1.08, x));
    const tcl = Math.min(1, tc);
    const e = tcl * tcl * (3 - 2 * tcl);
    const Lp = STRETCH_LEN + (TAU * R - STRETCH_LEN) * e;
    const kap = tc * TAU / Lp;
    const oy = -46 * (1 - tcl);
    const rot = th * tcl * 0.26 * Math.sin(tau * 0.9);
    const cr = Math.cos(rot), sr = Math.sin(rot);
    const at = (s: number) => {
      let px, py, nx, ny;
      if (kap < 1e-5) { px = s; py = 0; nx = 0; ny = 1; }
      else { px = Math.sin(kap * s) / kap; py = -(1 - Math.cos(kap * s)) / kap; nx = Math.sin(kap * s); ny = Math.cos(kap * s); }
      py += oy + R * tcl;
      return [px * cr - py * sr, px * sr + py * cr, nx * cr - ny * sr, nx * sr + ny * cr];
    };
    const f = (n: number) => n.toFixed(1);

    const ring = [];
    for (let q = 0; q <= 64; q++) { const p = at(-Lp / 2 + Lp * q / 64); ring.push(f(p[0]) + " " + f(p[1])); }
    const ringD = "M" + ring.join("L");
    ringA.setAttribute("d", ringD);
    ringB.setAttribute("d", ringD);

    const l = ["", "", "", ""], k = ["", "", "", ""];
    for (let i = 0; i < N; i++) {
      const mn = MAINS[i];
      const slot = (i + 0.5) / N;
      const u = mn ? mn[0] + (slot - mn[0]) * e : slot;
      const b = at(-Lp / 2 + u * Lp);
      const sway = reduced ? 0 : Math.sin(tau * 1.1 + i * 0.42) * 0.06 * (1 - tcl);
      const nx = b[2] * Math.cos(sway) - b[3] * Math.sin(sway);
      const ny = b[2] * Math.sin(sway) + b[3] * Math.cos(sway);
      let vis, base;
      if (mn) { vis = 1; base = mn[1] + (L_SHORT - mn[1]) * e; }
      else {
        const t0 = 0.25 + 0.45 * (rank[i] / 9);
        const w = Math.max(0, Math.min(1, (tcl - t0) / 0.3));
        vis = w * w * (3 - 2 * w); base = L_SHORT * vis;
      }
      if (vis < 0.02) continue;
      const wave = level == null ? 6 * Math.sin(tau * 6.5 - i * TAU / N * 2) : 14 * level * (0.6 + 0.4 * Math.sin(tau * 9 + i * 1.7));
      const L = base + (reduced ? 0 : vis * (sp * wave + th * 2 * Math.sin(tau * 2.5 + i)));
      const c = i % 4;
      l[c] += "M" + f(b[0]) + " " + f(b[1]) + "L" + f(b[0] + nx * L) + " " + f(b[1] + ny * L);
      const sc = Math.max(1, base / 30);
      for (const kd of knotDist[i]) {
        const dk = kd * sc;
        if (dk < L - 2) k[c] += "M" + f(b[0] + nx * dk) + " " + f(b[1] + ny * dk) + "l0 0";
      }
      if (sc > 1.3) { // the long knot near the tip, on the stretched khipu
        const dl = L - 9;
        k[c] += "M" + f(b[0] + nx * dl) + " " + f(b[1] + ny * dl) + "L" + f(b[0] + nx * (dl + 5)) + " " + f(b[1] + ny * (dl + 5));
      }
    }
    for (let c = 0; c < 4; c++) {
      lines[c].setAttribute("d", l[c] || "M0 0");
      knots[c].setAttribute("d", k[c] || "M0 0");
    }
  }

  function step(now: number) {
    if (last === null) last = now;
    const dt = Math.min(0.04, (now - last) / 1000);
    last = now;
    tau += dt;
    const target = TARGETS[mode];
    if (reduced) { x = target; v = 0; }
    else {
      v += (SPRING_W * SPRING_W * (target - x) - 2 * SPRING_Z * SPRING_W * v) * dt;
      x += v * dt;
    }
    const kk = Math.min(1, dt * 1.8);
    sp += ((mode === "speaking" ? 1 : 0) - sp) * kk;
    th += ((mode === "thinking" ? 1 : 0) - th) * kk;
    draw();
    raf = requestAnimationFrame(step);
  }

  draw();
  raf = requestAnimationFrame(step);

  return {
    setMode(m: CoronaMode) { mode = m; },
    // The loudness of the voice (0..1) while it speaks; null goes back to the built-in wave.
    setLevel(a: number | null) { level = a == null ? null : Math.max(0, Math.min(1, a)); },
    destroy() { cancelAnimationFrame(raf); [...lines, ...knots, ringA, ringB].forEach((p) => p.remove()); },
  };
}
