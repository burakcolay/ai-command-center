import { ChevronRight, FilePen, GitBranch, GitMerge, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { toolTarget } from "../lib/format";
import { AGENT_LABEL, STATUS_LABEL } from "../lib/labels";
import type { Decision, Task, TaskEvent, TaskStatus, TaskStepState } from "../lib/types";
import { ChecksPanel } from "./ChecksPanel";
import { DiffView } from "./DiffView";
import { StatusDot } from "./StatusDot";

const CANCELLABLE = new Set<TaskStatus>(["planning", "queued", "running", "paused"]);

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
  const review = task.status === "waiting_approval" && task.stage === "merge";

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
  const doneSteps = task.steps.filter((s) => s.status === "done").length;
  const resumeAt = task.resume_at
    ? new Date(task.resume_at).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" })
    : null;
  const statusLabel = review
    ? "İnceleme bekliyor"
    : task.status === "paused" && resumeAt
      ? `Kota bekleniyor · ${resumeAt}'de devam`
    : task.status === "running" && task.steps.length
      ? `Çalışıyor · ${Math.min(doneSteps + 1, task.steps.length)}/${task.steps.length}`
      : STATUS_LABEL[task.status];

  return (
    <div className="animate-rise rounded-xl border border-line bg-panel">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
        <span
          className={`inline-flex items-center gap-2 font-mono text-[10.5px] uppercase tracking-[0.14em] ${
            task.status === "failed" ? "text-danger" : "text-dim"
          }`}
        >
          <StatusDot status={task.status} />
          {statusLabel}
        </span>
        <div className="flex items-center gap-3 font-mono text-[10.5px] text-faint">
          {task.branch && task.stage !== "done" && (
            <span className="flex items-center gap-1" title="Görevin izole branch'i">
              <GitBranch size={11} /> {task.branch}
            </span>
          )}
          {task.adapter_id === "mock" && (
            <span className="rounded border border-line-strong px-1.5 text-dim">DEMO</span>
          )}
          <span>#{task.id}</span>
        </div>
      </div>

      <div className="px-4 py-4">
        {task.status === "planning" && !plan && (
          <LiveLine text={lineText(lastLine) || "Orchestrator isteği analiz ediyor"} />
        )}

        {plan && (
          <>
            <h3 className="text-[15px] font-medium text-fg">{plan.title}</h3>
            <p className="mt-1.5 text-[14px] leading-relaxed text-dim">{plan.summary}</p>
            {task.steps.length > 0 ? (
              <StepProgress steps={task.steps} />
            ) : (
              <PlanSteps task={task} />
            )}
            {task.stage === "plan" && plan.risks.length > 0 && (
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

        {task.status === "running" && (
          <div className="mt-3">
            <LiveLine text={lineText(lastLine) || "Ajan çalışıyor"} />
          </div>
        )}

        {task.status === "paused" && (
          <p className="mt-3 text-[13px] leading-relaxed text-dim">
            Claude abonelik kotası doldu. Görev{resumeAt ? ` ${resumeAt} civarında` : ""} kaldığı
            yerden kendiliğinden devam edecek; ücretli kullanıma geçilmez.
          </p>
        )}

        {(review || task.status === "completed") && task.checks && task.checks.length > 0 && (
          <div className="mt-4">
            <ChecksPanel
              results={task.checks}
              busy={busy}
              onFix={review ? () => decide("fix_checks") : undefined}
              onRerun={review ? () => decide("rerun_checks") : undefined}
            />
          </div>
        )}

        {review && (
          <div className="mt-4">
            <div className="label mb-2">
              Değişiklikler ·{" "}
              <span className="normal-case tracking-normal">
                {task.branch} → {task.base_branch}
              </span>
            </div>
            <DiffView taskId={task.id} version={`${task.stage}-${task.steps.length}`} />
          </div>
        )}

        {task.status === "failed" && task.error && (
          <p className="mt-3 whitespace-pre-wrap rounded-md border border-danger/30 bg-danger/[0.06] px-3 py-2 text-[13px] text-danger">
            {task.error}
          </p>
        )}
        {task.status === "queued" && (
          <p className="mt-3 font-mono text-[11px] text-faint">Sırada · başka bir görev bitince başlayacak.</p>
        )}
        {task.status === "completed" && (
          <p className="mt-3 flex items-center gap-2 font-mono text-[11px] text-dim">
            <GitMerge size={12} />
            {task.merged_commit
              ? `${task.base_branch} branch'ine birleştirildi · ${task.merged_commit.slice(0, 8)}`
              : "Tamamlandı · dosya değişikliği yok"}
          </p>
        )}

        {changing && (
          <div className="mt-4">
            <textarea
              autoFocus
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              placeholder={review ? "Ajan neyi düzeltsin?" : "Planda neyin değişmesini istiyorsun?"}
              className="w-full resize-none rounded-lg border border-line-strong bg-ink px-3 py-2 text-[13.5px] text-fg placeholder:text-faint focus:border-white/40 focus:outline-none"
            />
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-2">
          {task.status === "waiting_approval" &&
            (changing ? (
              <>
                <Btn primary disabled={busy || !note.trim()} onClick={() => decide("request_changes", note)}>
                  {review ? "Düzelt" : "Yeniden planla"}
                </Btn>
                <Btn onClick={() => setChanging(false)}>Vazgeç</Btn>
              </>
            ) : (
              <>
                <Btn primary disabled={busy} onClick={() => decide("approve")}>
                  {review ? "Birleştir" : "Onayla"}
                </Btn>
                <Btn disabled={busy} onClick={() => setChanging(true)}>
                  Değişiklik iste
                </Btn>
                <Btn disabled={busy} onClick={() => decide("reject")}>
                  Reddet
                </Btn>
              </>
            ))}
          {task.status === "paused" && (
            <Btn primary disabled={busy} onClick={() => decide("retry")}>
              Şimdi dene
            </Btn>
          )}
          {CANCELLABLE.has(task.status) && (
            <Btn disabled={busy} onClick={() => decide("cancel")}>
              İptal
            </Btn>
          )}
          {task.status === "failed" && (
            <Btn primary disabled={busy} onClick={() => decide("retry")}>
              {task.stage === "execute" ? "Kaldığı yerden devam et" : "Tekrar dene"}
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

function PlanSteps({ task }: { task: Task }) {
  return (
    <ol className="mt-4 space-y-px overflow-hidden rounded-lg border border-line">
      {task.plan!.steps.map((s, i) => (
        <li key={s.id} className="flex gap-3 bg-raised/60 px-3 py-2.5">
          <span className="pt-0.5 font-mono text-[11px] text-faint">{String(i + 1).padStart(2, "0")}</span>
          <div className="min-w-0 flex-1">
            <StepHeader title={s.title} agent={s.agent} writes={s.writes_files} />
            <p className="mt-0.5 text-[13px] leading-relaxed text-dim">{s.description}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

const STEP_DOT: Record<TaskStepState["status"], string> = {
  pending: "ring-1 ring-faint",
  running: "bg-white animate-pulse-dot",
  done: "bg-white",
  failed: "bg-danger",
};

function StepProgress({ steps }: { steps: TaskStepState[] }) {
  return (
    <ol className="mt-4 space-y-px overflow-hidden rounded-lg border border-line">
      {steps.map((s) => (
        <StepRow key={s.id} step={s} />
      ))}
    </ol>
  );
}

function StepRow({ step }: { step: TaskStepState }) {
  const [open, setOpen] = useState(false);
  const title = step.kind === "revision" ? `Geri bildirim: ${step.description}` : step.title;
  return (
    <li className={`bg-raised/60 px-3 py-2.5 ${step.status === "pending" ? "opacity-60" : ""}`}>
      <div className="flex gap-3">
        <span className={`mt-[7px] inline-block size-1.5 shrink-0 rounded-full ${STEP_DOT[step.status]}`} />
        <div className="min-w-0 flex-1">
          <StepHeader title={title} agent={step.agent} />
          {step.summary && (
            <>
              <p
                className={`mt-1 whitespace-pre-wrap text-[13px] leading-relaxed text-dim ${
                  open ? "" : "line-clamp-2"
                }`}
              >
                {step.summary}
              </p>
              <button
                onClick={() => setOpen((o) => !o)}
                className="mt-0.5 font-mono text-[10.5px] text-faint hover:text-fg"
              >
                {open ? "daha az" : "özetin tamamı"}
              </button>
            </>
          )}
        </div>
        {step.commit && (
          <span className="shrink-0 pt-0.5 font-mono text-[10.5px] text-faint" title="Bu adımın commit'i">
            {step.commit.slice(0, 7)}
          </span>
        )}
      </div>
    </li>
  );
}

function StepHeader({ title, agent, writes }: { title: string; agent: string; writes?: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-[13.5px] text-fg">{title}</span>
      <span className="rounded-full border border-line-strong px-2 font-mono text-[10px] leading-[18px] text-dim">
        {AGENT_LABEL[agent] ?? agent}
      </span>
      {writes && (
        <span className="flex items-center gap-1 font-mono text-[10px] text-dim" title="Bu adım dosya değiştirir">
          <FilePen size={11} /> yazar
        </span>
      )}
    </div>
  );
}

function LiveLine({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-3 text-[13.5px] text-dim">
      <ScanDots />
      <span className="truncate">{text}</span>
    </div>
  );
}

function EventLog({ events }: { events: TaskEvent[] | undefined }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" });
  }, [events?.length]);
  return (
    <div className="max-h-72 overflow-y-auto border-t border-line bg-ink px-4 py-3 font-mono text-[11.5px] leading-5">
      {events === undefined && <div className="text-faint">yükleniyor…</div>}
      {events?.length === 0 && <div className="text-faint">kayıt yok</div>}
      {events?.map((e) => (
        <div key={e.id} className={`flex gap-3 ${e.kind === "error" ? "text-danger" : "text-dim"}`}>
          <span className="shrink-0 text-faint">
            {new Date(e.created_at).toLocaleTimeString("tr-TR", { hour12: false })}
          </span>
          {typeof e.data.step === "string" && <span className="shrink-0 text-faint">{e.data.step}</span>}
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
  if (e.kind === "tool") return `▸ ${d.name} ${toolTarget(d.input)}`;
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
    <span className="flex shrink-0 gap-1" aria-hidden>
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
