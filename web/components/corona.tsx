"use client";

import { type Ref, useEffect, useImperativeHandle, useRef } from "react";

import { type CoronaMode, createCorona } from "@/lib/quipu-corona";

export type CoronaHandle = { setLevel: (level: number | null) => void };

// Quipu's large avatar. `mode` follows what the agent is doing; `ref.setLevel` feeds it the
// loudness of the voice while it speaks.
export function Corona({ mode, ref }: { mode: CoronaMode; ref?: Ref<CoronaHandle> }) {
  const svg = useRef<SVGSVGElement>(null);
  const corona = useRef<ReturnType<typeof createCorona> | null>(null);

  useEffect(() => {
    const created = createCorona(svg.current!);
    corona.current = created;
    return () => created.destroy();
  }, []);

  useEffect(() => corona.current?.setMode(mode), [mode]);

  useImperativeHandle(ref, () => ({ setLevel: (level) => corona.current?.setLevel(level) }), []);

  return (
    <svg ref={svg} width="100%" height="100%" viewBox="-100 -100 200 200" fill="none" aria-hidden="true" style={{ overflow: "visible" }} />
  );
}
