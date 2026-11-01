import { STATUS_LABEL } from "../lib/labels";
import type { TaskStatus } from "../lib/types";

const STYLE: Record<TaskStatus, string> = {
  planning: "bg-white animate-pulse-dot",
  running: "bg-white animate-pulse-dot",
  waiting_approval: "ring-1 ring-white bg-white/40 animate-blink",
  queued: "ring-1 ring-white/70",
  paused: "ring-1 ring-faint",
  completed: "bg-white",
  failed: "bg-danger",
  cancelled: "bg-faint",
};

export function StatusDot({ status }: { status: TaskStatus }) {
  return <span className={`inline-block size-1.5 shrink-0 rounded-full ${STYLE[status]}`} />;
}

export function StatusPill({ status }: { status: TaskStatus }) {
  return (
    <span
      className={`inline-flex items-center gap-2 font-mono text-[10.5px] uppercase tracking-[0.14em] ${
        status === "failed" ? "text-danger" : "text-dim"
      }`}
    >
      <StatusDot status={status} />
      {STATUS_LABEL[status]}
    </span>
  );
}

const MODEL_DOT: Record<string, string> = {
  available: "bg-white",
  limited: "bg-white/50",
  cooldown: "ring-1 ring-white animate-blink",
  paid_access_required: "bg-danger",
};

export function ModelDot({ state }: { state: string }) {
  return (
    <span
      className={`inline-block size-1.5 shrink-0 rounded-full ${MODEL_DOT[state] ?? "ring-1 ring-faint"}`}
    />
  );
}
