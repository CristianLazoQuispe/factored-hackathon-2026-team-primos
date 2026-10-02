import { Bot, User } from "lucide-react";

// Who wrote a message: the assistant (a robot) or a person of the team.
export function SpeakerIcon({ person }: { person: boolean }) {
  const Icon = person ? User : Bot;
  return (
    <span
      role="img"
      aria-label={person ? "Persona" : "Asistente"}
      className={`mt-1 flex size-7 shrink-0 items-center justify-center rounded-full ${
        person ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
      }`}
    >
      <Icon className="size-4" />
    </span>
  );
}
