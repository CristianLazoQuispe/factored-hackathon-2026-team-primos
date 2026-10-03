import Link from "next/link";
import type { ReactNode } from "react";

import { Logo } from "@/components/logo";

// The two sides of the product, each with its own tabs.
const TABS = {
  cliente: [
    { href: "/chat", label: "Chat" },
    { href: "/mis-finanzas", label: "Mis finanzas" },
  ],
  consola: [
    { href: "/consola", label: "Conversaciones" },
    { href: "/consola/perfil", label: "Perfil 360" },
    { href: "/consola/gerencia", label: "Panel de gerencia" },
  ],
};

// The top bar of every screen but the landing. `children` go on the right.
export function AppHeader({ area, active, children }: { area: keyof typeof TABS; active: string; children?: ReactNode }) {
  return (
    <header
      style={{
        display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 14,
        padding: "14px 24px", borderBottom: "1px solid rgba(230,244,241,.07)",
      }}
    >
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 16 }}>
        <Link href="/" className="q-st-idle" style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none", color: "var(--q-mist)" }}>
          <Logo animated />
          <span style={{ fontWeight: 600, fontSize: 18, letterSpacing: "-0.03em" }}>quipu</span>
        </Link>
        <nav style={{ display: "flex", flexWrap: "wrap", gap: 4, padding: 4, borderRadius: 12, boxShadow: "inset 0 0 0 1px rgba(230,244,241,.08)" }}>
          {TABS[area].map((tab) => (
            <Link key={tab.href} href={tab.href} className={tab.href === active ? "q-tab q-tab-on" : "q-tab"}>
              {tab.label}
            </Link>
          ))}
        </nav>
      </div>
      {children}
    </header>
  );
}
