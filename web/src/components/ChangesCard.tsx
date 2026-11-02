import {
  ArrowUpRight,
  ChevronRight,
  Eye,
  GitBranch,
  GitMerge,
  GitPullRequest,
  Undo2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "../lib/api";
import { toolTarget } from "../lib/format";
import type { Decision, GitHubStatus, Task, TaskEvent, TaskStepState } from "../lib/types";
import { ChecksPanel } from "./ChecksPanel";
import { DiffView } from "./DiffView";
import { PreviewPanel } from "./PreviewPanel";
import { StatusDot } from "./StatusDot";

interface Props {
  task: Task;
  events: TaskEvent[] | undefined;
  onLoadEvents: (taskId: number) => void;
  /** Put text in the composer (e.g. "fix the failing checks"). */
  onAsk: (text: string) => void;
  onError: (msg: string) => void;
}

const FIX_TEXT = "Başarısız kalite kontrollerini düzelt.";

/** What the assistant changed in the project during this chat: review, merge, undo, discard. */
export function ChangesCard({ task, events, onLoadEvents, onAsk, onError }: Props) {
  const [logOpen, setLogOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  // An iOS preview asks first (the app runs in the Simulator with the user's rights); the
  // server's question is shown as is and only a yes repeats the request with that consent.
  const preview = async (opts: { allow_device?: boolean; unsandboxed?: boolean } = {}) => {
    setBusy(true);
    try {
      await api.preview(task.id, opts);
    } catch (e) {
      if (e instanceof ApiError && e.status === 428) {
        if (window.confirm(e.message)) await preview({ ...opts, allow_device: true });
      } else {
        onError((e as Error).message);
      }
    } finally {
      setBusy(false);
    }
  };
  const working = task.status === "running" || task.status === "queued";
  const review = task.status === "waiting_approval";
  const steps = task.steps;
  const canUndo = steps.some((s) => s.status === "done" && s.commit);

  useEffect(() => {
    if (logOpen && events === undefined) onLoadEvents(task.id);
  }, [logOpen, events, task.id, onLoadEvents]);

  // Only projects on GitHub get the pull-request button.
  const [github, setGithub] = useState<GitHubStatus | null>(null);
  useEffect(() => {
    if (!review) return;
    api.github(task.id).then(setGithub).catch(() => setGithub(null));
  }, [review, task.id]);

  const decide = async (d: Decision) => {
    setBusy(true);
    try {
      await api.decide(task.id, d);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const status =
    task.status === "completed"
      ? "Projeye birleştirildi"
      : task.status === "cancelled"
        ? "Değişiklikler atıldı"
        : working
          ? "Asistan çalışıyor"
          : canUndo
            ? "Değişiklikler hazır"
            : "Değişiklik kalmadı";

  return (
    <div className="animate-rise rounded-xl border border-line bg-panel">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
        <span className="inline-flex items-center gap-2 font-mono text-[10.5px] uppercase tracking-[0.14em] text-dim">
          <StatusDot status={task.status} />
          {status}
        </span>
        <div className="flex items-center gap-3 font-mono text-[10.5px] text-faint">
          {task.branch && review && (
            <span className="flex items-center gap-1" title="Değişikliklerin tutulduğu izole branch">
              <GitBranch size={11} /> {task.branch} → {task.base_branch}
            </span>
          )}
          <span>#{task.id}</span>
        </div>
      </div>

      <div className="px-4 py-4">
        {(review || working) && (
          <p className="text-[13px] leading-relaxed text-dim">
            Değişiklikler projenin bir kopyasında. Sen birleştirene kadar gerçek projene hiçbir şey
            yazılmaz. Başka bir şey istersen sohbete yazmaya devam et.
          </p>
        )}

        {steps.length > 0 && (
          <ol className="mt-3 space-y-px overflow-hidden rounded-lg border border-line">
            {steps.map((s) => (
              <StepRow key={s.id} step={s} />
            ))}
          </ol>
        )}

        {review && task.checks && task.checks.length > 0 && (
          <div className="mt-4">
            <ChecksPanel
              results={task.checks}
              busy={busy}
              onFix={() => onAsk(FIX_TEXT)}
              onRerun={() => void decide("rerun_checks")}
            />
          </div>
        )}

        {task.preview && task.preview.status !== "unsupported" && (
          <div className="mt-4">
            <PreviewPanel
              preview={task.preview}
              onFix={onAsk}
              onBuildOutsideSandbox={() => {
                const question = task.preview?.confirm;
                if (question && window.confirm(question)) {
                  void preview({ allow_device: true, unsandboxed: true });
                }
              }}
            />
          </div>
        )}
        {task.preview?.status === "unsupported" && (
          <p className="mt-3 font-mono text-[10.5px] text-faint">{task.preview.reason}</p>
        )}

        {review && canUndo && (
          <div className="mt-4">
            <DiffView taskId={task.id} version={steps.map((s) => s.status).join()} />
          </div>
        )}

        {task.pr_url && (
          <a
            href={task.pr_url}
            target="_blank"
            rel="noreferrer"
            className="mt-3 inline-flex items-center gap-1.5 font-mono text-[11px] text-dim hover:text-fg"
          >
            <GitPullRequest size={12} />
            GitHub'da PR #{task.pr_url.split("/").pop()}
            <ArrowUpRight size={11} />
          </a>
        )}

        {task.status === "completed" && task.merged_commit && (
          <p className="mt-3 flex items-center gap-2 font-mono text-[11px] text-dim">
            <GitMerge size={12} />
            {task.base_branch} branch'ine birleştirildi · {task.merged_commit.slice(0, 8)}
          </p>
        )}

        {review && github?.repo && !github.ready && (
          <p className="mt-3 font-mono text-[10.5px] text-faint">PR için: {github.reason}</p>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-2">
          {review && (
            <>
              <Btn primary disabled={busy || !canUndo} onClick={() => void decide("approve")}>
                Birleştir
              </Btn>
              <Btn disabled={busy || !canUndo} onClick={() => void decide("undo_last")}>
                <span className="flex items-center gap-1.5">
                  <Undo2 size={13} /> Son değişikliği geri al
                </span>
              </Btn>
              <Btn
                disabled={busy || task.preview?.status === "running"}
                onClick={() => void preview()}
                title="Web: sandbox'ta derleyip internetsiz bir tarayıcıda telefon ve masaüstü görüntüsü. iOS: Xcode ile derleyip Simülatör'de ekran görüntüsü (onayınla)."
              >
                <span className="flex items-center gap-1.5">
                  <Eye size={13} /> Önizle
                </span>
              </Btn>
              {github?.repo && (
                <Btn
                  disabled={busy || !canUndo || !github.ready}
                  onClick={() => void decide("open_pr")}
                  title={
                    github.ready
                      ? `Değişiklikleri ${github.repo} deposuna ayrı bir branch olarak gönderir`
                      : github.reason
                  }
                >
                  <span className="flex items-center gap-1.5">
                    <GitPullRequest size={13} /> {task.pr_url ? "PR'ı güncelle" : "GitHub'da PR aç"}
                  </span>
                </Btn>
              )}
              <Btn disabled={busy} onClick={() => void decide("reject")}>
                Hepsini at
              </Btn>
            </>
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

function StepRow({ step }: { step: TaskStepState }) {
  const reverted = step.status === "reverted";
  return (
    <li className={`flex gap-3 bg-raised/60 px-3 py-2 ${reverted ? "opacity-50" : ""}`}>
      <span
        className={`mt-[7px] inline-block size-1.5 shrink-0 rounded-full ${
          reverted ? "ring-1 ring-faint" : "bg-white"
        }`}
      />
      <div className="min-w-0 flex-1">
        <div className="line-clamp-2 text-[13px] text-fg">{step.title}</div>
        {reverted && <div className="mt-0.5 font-mono text-[10.5px] text-faint">geri alındı</div>}
      </div>
      {step.commit && !reverted && (
        <span className="shrink-0 pt-0.5 font-mono text-[10.5px] text-faint" title="Bu değişikliğin commit'i">
          {step.commit.slice(0, 7)}
        </span>
      )}
    </li>
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
          <span className="break-all">{lineText(e)}</span>
        </div>
      ))}
      <div ref={end} />
    </div>
  );
}

function lineText(e: TaskEvent): string {
  const d = e.data as Record<string, unknown>;
  if (e.kind === "tool") return `▸ ${d.name} ${toolTarget(d.input)}`;
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
