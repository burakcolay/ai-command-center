import { ChevronRight, FilePen, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { AGENT_LABEL } from "../lib/labels";
import type { Decision, Task, TaskEvent } from "../lib/types";
import { StatusPill } from "./StatusDot";

interface Props {
  task: Task;
  events: TaskEvent[] | undefined;
  onLoadEvents: (taskId: number) => void;
  onError: (msg: string) => void;
}

export function TaskCard({ task, events, onLoadEvents, onError }: Props) {
  const [logOpen, setLogOpen] = useState(false);
  const [changing, setChanging] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const live = task.status === "planning" || task.status === "running";

  useEffect(() => {
    if ((logOpen || live) && events === undefined) onLoadEvents(task.id);
  }, [logOpen, live, events, task.id, onLoadEvents]);

  const decide = async (d: Decision, n?: string) => {
    setBusy(true);
    try {
      await api.decide(task.id, d, n);
      setChanging(false);
      setNote("");
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const plan = task.plan;
  const lastLine = events?.filter((e) => e.kind !== "usage").at(-1);

  return (
    <div className="animate-rise rounded-xl border border-line bg-panel">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
        <StatusPill status={task.status} />
        <div className="flex items-center gap-3 font-mono text-[10.5px] text-faint">
          {task.adapter_id === "mock" && (
            <span className="rounded border border-line-strong px-1.5 text-dim">DEMO</span>
          )}
          <span>#{task.id}</span>
        </div>
      </div>

      <div className="px-4 py-4">
        {task.status === "planning" && !plan && (
          <div className="flex items-center gap-3 text-[14px] text-dim">
            <ScanDots />
            <span className="truncate">{lineText(lastLine) || "Orchestrator isteği analiz ediyor"}</span>
          </div>
        )}

        {plan && (
          <>
            <h3 className="text-[15px] font-medium text-fg">{plan.title}</h3>
            <p className="mt-1.5 text-[14px] leading-relaxed text-dim">{plan.summary}</p>
            <ol className="mt-4 space-y-px overflow-hidden rounded-lg border border-line">
              {plan.steps.map((s, i) => (
                <li key={s.id} className="flex gap-3 bg-raised/60 px-3 py-2.5">
                  <span className="pt-0.5 font-mono text-[11px] text-faint">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[13.5px] text-fg">{s.title}</span>
                      <span className="rounded-full border border-line-strong px-2 font-mono text-[10px] leading-[18px] text-dim">
                        {AGENT_LABEL[s.agent] ?? s.agent}
                      </span>
                      {s.writes_files && (
                        <span
                          className="flex items-center gap-1 font-mono text-[10px] text-dim"
                          title="Bu adım dosya değiştirir"
                        >
                          <FilePen size={11} /> yazar
                        </span>
                      )}
                    </div>
                    <p className="mt-0.5 text-[13px] leading-relaxed text-dim">{s.description}</p>
                  </div>
                </li>
              ))}
            </ol>
            {plan.risks.length > 0 && (
              <ul className="mt-3 space-y-1">
                {plan.risks.map((r) => (
                  <li key={r} className="flex gap-2 text-[12.5px] text-dim">
                    <TriangleAlert size={12} className="mt-0.5 shrink-0 text-faint" />
                    {r}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}

        {task.status === "failed" && task.error && (
          <p className="mt-3 rounded-md border border-danger/30 bg-danger/[0.06] px-3 py-2 text-[13px] text-danger">
            {task.error}
          </p>
        )}
        {task.status === "queued" && (
          <p className="mt-3 font-mono text-[11px] text-faint">
            Onaylandı · yürütme motoru (izole worktree) bir sonraki sürümde.
          </p>
        )}

        {changing && (
          <div className="mt-4">
            <textarea
              autoFocus
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              placeholder="Planda neyin değişmesini istiyorsun?"
              className="w-full resize-none rounded-lg border border-line-strong bg-ink px-3 py-2 text-[13.5px] text-fg placeholder:text-faint focus:border-white/40 focus:outline-none"
            />
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-2">
          {task.status === "waiting_approval" &&
            (changing ? (
              <>
                <Btn primary disabled={busy || !note.trim()} onClick={() => decide("request_changes", note)}>
                  Yeniden planla
                </Btn>
                <Btn onClick={() => setChanging(false)}>Vazgeç</Btn>
              </>
            ) : (
              <>
                <Btn primary disabled={busy} onClick={() => decide("approve")}>
                  Onayla
                </Btn>
                <Btn disabled={busy} onClick={() => setChanging(true)}>
                  Değişiklik iste
                </Btn>
                <Btn disabled={busy} onClick={() => decide("reject")}>
                  Reddet
                </Btn>
              </>
            ))}
          {(task.status === "planning" || task.status === "queued") && (
            <Btn disabled={busy} onClick={() => decide("cancel")}>
              İptal
            </Btn>
          )}
          {task.status === "failed" && (
            <Btn primary disabled={busy} onClick={() => decide("retry")}>
              Tekrar dene
            </Btn>
          )}
          <button
            onClick={() => setLogOpen((o) => !o)}
            className="ml-auto flex items-center gap-1 font-mono text-[10.5px] uppercase tracking-[0.14em] text-faint hover:text-fg"
            aria-expanded={logOpen}
          >
            <ChevronRight size={12} className={`transition-transform ${logOpen ? "rotate-90" : ""}`} />
            Günlük
          </button>
        </div>
      </div>

      {logOpen && <EventLog events={events} />}
    </div>
  );
}

function EventLog({ events }: { events: TaskEvent[] | undefined }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" });
  }, [events?.length]);
  return (
    <div className="max-h-64 overflow-y-auto border-t border-line bg-ink px-4 py-3 font-mono text-[11.5px] leading-5">
      {events === undefined && <div className="text-faint">yükleniyor…</div>}
      {events?.length === 0 && <div className="text-faint">kayıt yok</div>}
      {events?.map((e) => (
        <div key={e.id} className={`flex gap-3 ${e.kind === "error" ? "text-danger" : "text-dim"}`}>
          <span className="shrink-0 text-faint">
            {new Date(e.created_at).toLocaleTimeString("tr-TR", { hour12: false })}
          </span>
          <span className="break-all">{lineText(e)}</span>
        </div>
      ))}
      <div ref={end} />
    </div>
  );
}

function lineText(e: TaskEvent | undefined): string {
  if (!e) return "";
  const d = e.data as Record<string, unknown>;
  if (e.kind === "tool") {
    const input = d.input ? JSON.stringify(d.input) : "";
    return `▸ ${d.name} ${input.length > 120 ? `${input.slice(0, 120)}…` : input}`;
  }
  if (e.kind === "usage") {
    const ws = (d.windows as { name: string; utilization: number | null }[]) ?? [];
    return `limit · ${ws.map((w) => `${w.name} %${Math.round((w.utilization ?? 0) * 100)}`).join(" · ")}`;
  }
  return String(d.text ?? "");
}

function Btn({
  primary,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { primary?: boolean }) {
  return (
    <button
      {...rest}
      className={`rounded-lg px-3.5 py-1.5 text-[13px] transition-colors disabled:opacity-30 ${
        primary
          ? "bg-white font-medium text-black hover:bg-white/85"
          : "border border-line-strong text-fg hover:border-white/40"
      }`}
    />
  );
}

/** Three dots scanning left to right: the "thinking" indicator. */
function ScanDots() {
  return (
    <span className="flex gap-1" aria-hidden>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="size-1.5 rounded-full bg-white animate-pulse-dot"
          style={{ animationDelay: `${i * 180}ms` }}
        />
      ))}
    </span>
  );
}
