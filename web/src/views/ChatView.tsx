import { Zap } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Composer } from "../components/Composer";
import { DotMatrix } from "../components/DotMatrix";
import { TaskCard } from "../components/TaskCard";
import { toolTarget } from "../lib/format";
import type { ComposerMode, Message, Project, Task, TaskEvent } from "../lib/types";

const SUGGESTIONS: Record<ComposerMode, string[]> = {
  chat: [
    "Aklımda bir uygulama fikri var, birlikte netleştirelim",
    "Bu projenin mimarisini bana anlat",
    "Bu projede en çok neyi iyileştirmeliyim?",
  ],
  task: [
    "README dosyasını mevcut kod yapısına göre yeniden yaz",
    "Test kapsamını incele ve eksik testleri ekle",
  ],
};

const CONVERT_TEXT = "Sohbette kararlaştırdıklarımızı uygula.";

interface Props {
  messages: Message[];
  tasks: Record<number, Task>;
  events: Record<number, TaskEvent[]>;
  activity: Record<number, string>;
  projects: Project[];
  projectId: number | null;
  mode: ComposerMode;
  demoMode: boolean;
  onModeChange: (m: ComposerMode) => void;
  onProjectChange: (id: number | null) => void;
  onSend: (text: string) => Promise<void>;
  onStop: (messageId: number) => void;
  onLoadEvents: (taskId: number) => void;
  onError: (msg: string) => void;
}

export function ChatView(p: Props) {
  const scroller = useRef<HTMLDivElement>(null);
  const [prefill, setPrefill] = useState<{ text: string; nonce: number }>();
  const last = p.messages.at(-1);
  const lastTaskStatus = last?.task_id ? p.tasks[last.task_id]?.status : undefined;
  const streaming = p.messages.find((m) => m.status === "streaming");

  // Follow new content, but only if the user hasn't scrolled up to read.
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 160) el.scrollTop = el.scrollHeight;
  }, [p.messages.length, last?.content.length, lastTaskStatus]);

  const convert = () => {
    p.onModeChange("task");
    setPrefill({ text: CONVERT_TEXT, nonce: Date.now() });
  };

  const composer = (
    <Composer
      projects={p.projects}
      projectId={p.projectId}
      onProjectChange={p.onProjectChange}
      mode={p.mode}
      onModeChange={p.onModeChange}
      onSend={p.onSend}
      prefill={prefill}
      onStop={streaming ? () => p.onStop(streaming.id) : undefined}
      autoFocus
    />
  );

  if (p.messages.length === 0) {
    return (
      <div className="relative flex h-full flex-col items-center justify-center px-4">
        <div className="dot-grid pointer-events-none absolute inset-0" aria-hidden />
        <div className="relative w-full max-w-2xl">
          <div className="mb-8 flex flex-col items-center gap-5 text-center">
            <DotMatrix text="ORBIT" dot={6} gap={3} className="max-w-full" />
            <div className="label tracking-[0.3em]">AI Komuta Merkezi</div>
            <p className="text-[15px] text-dim">Bugün ne inşa ediyoruz?</p>
          </div>
          {composer}
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            {SUGGESTIONS[p.mode].map((s) => (
              <button
                key={s}
                onClick={() => void p.onSend(s)}
                className="rounded-full border border-line px-3 py-1.5 text-[12.5px] text-dim transition-colors hover:border-white/30 hover:text-fg"
              >
                {s}
              </button>
            ))}
          </div>
          <p className="mt-6 text-center text-[12px] leading-relaxed text-faint">
            {p.mode === "chat"
              ? "Sohbet modunda hiçbir dosya değişmez. Karar verdiğinde sohbeti göreve dönüştür."
              : "Görev modunda Orchestrator bir plan çıkarır; onayından sonra ajanlar uygular."}
            {p.demoMode && " · DEMO MODU açık"}
          </p>
        </div>
      </div>
    );
  }

  const lastAssistant = [...p.messages].reverse().find((m) => m.role === "assistant");

  return (
    <div className="flex h-full flex-col">
      <div ref={scroller} className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-8">
          {p.messages.map((m) => {
            if (m.role === "user") {
              return (
                <div key={m.id} className="flex justify-end animate-rise">
                  <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-white/[0.08] px-4 py-2.5 text-[14.5px] leading-relaxed text-fg">
                    {m.content}
                  </div>
                </div>
              );
            }
            if (m.role === "task") {
              const t = m.task_id ? p.tasks[m.task_id] : undefined;
              return t ? (
                <TaskCard
                  key={m.id}
                  task={t}
                  events={p.events[t.id]}
                  onLoadEvents={p.onLoadEvents}
                  onError={p.onError}
                />
              ) : null;
            }
            return (
              <AssistantMessage
                key={m.id}
                message={m}
                activity={p.activity[m.id]}
                canConvert={m.id === lastAssistant?.id && m.status === "done" && last?.id === m.id}
                onConvert={convert}
              />
            );
          })}
        </div>
      </div>
      <div className="mx-auto w-full max-w-3xl px-4 pb-4">{composer}</div>
    </div>
  );
}

function AssistantMessage({
  message: m,
  activity,
  canConvert,
  onConvert,
}: {
  message: Message;
  activity?: string;
  canConvert: boolean;
  onConvert: () => void;
}) {
  const streaming = m.status === "streaming";
  return (
    <div className="animate-rise">
      {m.content ? (
        <div className={m.status === "error" ? "md text-danger" : "md"}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
        </div>
      ) : null}
      {streaming && (
        <div className="mt-2 flex items-center gap-3 font-mono text-[11.5px] text-faint">
          <span className="flex shrink-0 gap-1" aria-hidden>
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="size-1.5 rounded-full bg-white animate-pulse-dot"
                style={{ animationDelay: `${i * 180}ms` }}
              />
            ))}
          </span>
          <span className="truncate">{activity ?? (m.content ? "yazıyor" : "düşünüyor")}</span>
        </div>
      )}
      {canConvert && (
        <button
          onClick={onConvert}
          className="mt-3 flex items-center gap-1.5 rounded-full border border-line-strong px-3 py-1 font-mono text-[11px] tracking-wide text-dim transition-colors hover:border-white hover:text-fg"
          title="Bu sohbeti plana dönüştür; onayından sonra ajanlar uygular"
        >
          <Zap size={11} /> Göreve dönüştür
        </button>
      )}
    </div>
  );
}

export function activityText(tool: { name: string; input?: unknown }): string {
  return `▸ ${tool.name} ${toolTarget(tool.input)}`.trim();
}
