import { ChevronRight } from "lucide-react";
import { useState } from "react";
import type { TeamMember, TeamPicture, TeamStatus } from "../lib/types";

const EFFORT_DOTS: Record<string, number> = { low: 1, medium: 2, high: 3, xhigh: 4, max: 5 };

export function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(".", ",")}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1).replace(".", ",")}k`;
  return String(n);
}

/** Effort as a row of five dots: how hard this member thinks. */
function Effort({ level }: { level: string }) {
  const lit = EFFORT_DOTS[level] ?? 0;
  if (!lit) return null;
  return (
    <span className="inline-flex items-center gap-[3px]" title={`efor: ${level}`} aria-label={`efor ${level}`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} className={`size-[4px] rounded-full ${i <= lit ? "bg-white" : "bg-white/15"}`} />
      ))}
      <span className="ml-1 font-mono text-[10px] text-faint">{level}</span>
    </span>
  );
}

function Dot({ status }: { status: TeamStatus }) {
  const cls =
    status === "running"
      ? "bg-white animate-pulse-dot"
      : status === "failed"
        ? "bg-danger"
        : "bg-white/60";
  return <span className={`mt-[6px] inline-block size-1.5 shrink-0 rounded-full ${cls}`} aria-hidden />;
}

function Row({
  label,
  vendor,
  model,
  effort,
  status,
  line,
  tokens,
  child,
  last,
}: {
  label: string;
  vendor: string;
  model: string;
  effort: string;
  status: TeamStatus;
  line: string;
  tokens?: number;
  child?: boolean;
  last?: boolean;
}) {
  return (
    <div className={`relative flex gap-2.5 py-1.5 ${child ? "pl-6" : ""}`}>
      {child && (
        <span
          className={`absolute left-[3px] top-0 w-4 border-l border-line-strong ${last ? "h-[13px]" : "h-full"}`}
          aria-hidden
        >
          <span className="absolute left-0 top-[12px] w-3 border-t border-line-strong" />
        </span>
      )}
      <Dot status={status} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <span className="text-[13px] text-fg">{label}</span>
          <span className="rounded border border-line-strong px-1.5 font-mono text-[10px] leading-[16px] text-dim">
            {vendor}
            {model && <span className="text-fg"> · {model}</span>}
          </span>
          <Effort level={effort} />
          {tokens ? <span className="font-mono text-[10px] text-faint">{formatTokens(tokens)} token</span> : null}
        </div>
        {line && <div className="truncate font-mono text-[10.5px] text-faint">{line}</div>}
      </div>
    </div>
  );
}

function memberLine(m: TeamMember): string {
  if (m.status === "failed") return "başarısız";
  if (m.status === "running") return m.activity || m.task || "çalışıyor";
  return m.activity || m.task;
}

/** The live orchestra of a turn: the conductor, its team, what each is doing, what it costs. */
export function Orchestra({ team, live }: { team: TeamPicture; live: boolean }) {
  const [open, setOpen] = useState(false);
  const members = team.members;
  const lead = team.lead;
  const leadModel = lead.actual || lead.model;
  const totals = Object.entries(team.usage ?? {});
  const total = totals.reduce((sum, [, u]) => sum + u.input + u.output, 0);

  if (!members.length) {
    // A turn without a team: just who answered, on what.
    if (!leadModel) return null;
    return (
      <div className="mt-2 flex items-center gap-2 font-mono text-[10px] text-faint">
        <span>
          {lead.vendor} · {leadModel}
        </span>
        <Effort level={lead.effort} />
        {total > 0 && <span>· {formatTokens(total)} token</span>}
      </div>
    );
  }

  const running = members.filter((m) => m.status === "running").length;
  const expanded = live || open;
  return (
    <div className="mb-3 overflow-hidden rounded-xl border border-line bg-panel/70">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 border-b border-line px-3 py-2 text-left"
        aria-expanded={expanded}
      >
        <ChevronRight size={12} className={`text-faint transition-transform ${expanded ? "rotate-90" : ""}`} />
        <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-dim">Orkestra</span>
        <span className="font-mono text-[10.5px] text-faint">
          {members.length} ajan{running ? ` · ${running} çalışıyor` : ""}
          {total > 0 ? ` · ${formatTokens(total)} token` : ""}
        </span>
      </button>
      {expanded && (
        <div className="px-3 py-2">
          <Row
            label={lead.label}
            vendor={lead.vendor}
            model={leadModel}
            effort={lead.effort}
            status={lead.status}
            line={lead.status === "running" ? lead.activity || "yönetiyor" : ""}
          />
          {members.map((m, i) => (
            <Row
              key={m.id}
              child
              last={i === members.length - 1}
              label={m.label}
              vendor={m.vendor}
              model={m.actual || m.model}
              effort={m.effort}
              status={m.status}
              line={memberLine(m)}
              tokens={m.tokens}
            />
          ))}
          {totals.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 border-t border-line pt-2 font-mono text-[10px] text-faint">
              {totals.map(([model, u]) => (
                <span key={model} title={`önbellekten okunan: ${formatTokens(u.cached)}`}>
                  {model}: {formatTokens(u.input)} girdi · {formatTokens(u.output)} çıktı
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
