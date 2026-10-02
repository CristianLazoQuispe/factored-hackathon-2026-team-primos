import { Bot, Headset, User } from "lucide-react";

export type Speaker = "customer" | "assistant" | "operator";

// Each speaker has one icon and one colour, the same in the customer chat and in the console.
const SPEAKERS = {
  customer: { Icon: User, label: "Cliente", icon: "bg-sky-200 text-sky-900", bubble: "bg-sky-100 text-sky-950" },
  assistant: {
    Icon: Bot,
    label: "Asistente",
    icon: "bg-violet-200 text-violet-900",
    bubble: "bg-violet-100 text-violet-950",
  },
  operator: {
    Icon: Headset,
    label: "Soporte",
    icon: "bg-emerald-200 text-emerald-900",
    bubble: "bg-emerald-100 text-emerald-950",
  },
};

export function bubbleColor(speaker: Speaker) {
  return SPEAKERS[speaker].bubble;
}

export function SpeakerIcon({ speaker }: { speaker: Speaker }) {
  const { Icon, label, icon } = SPEAKERS[speaker];
  return (
    <span
      role="img"
      aria-label={label}
      className={`mt-1 flex size-7 shrink-0 items-center justify-center rounded-full ${icon}`}
    >
      <Icon className="size-4" />
    </span>
  );
}
