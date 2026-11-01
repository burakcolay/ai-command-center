import { useEffect, useRef } from "react";
import { Composer } from "../components/Composer";
import { DotMatrix } from "../components/DotMatrix";
import { TaskCard } from "../components/TaskCard";
import type { Message, Project, Task, TaskEvent } from "../lib/types";

const SUGGESTIONS = [
  "Bu projenin mimarisini analiz et, iyileştirme planı hazırla",
  "README dosyasını mevcut kod yapısına göre yeniden yaz",
  "Test kapsamını incele ve eksik testleri listele",
];

interface Props {
  messages: Message[];
  tasks: Record<number, Task>;
  events: Record<number, TaskEvent[]>;
  projects: Project[];
  projectId: number | null;
  demoMode: boolean;
  onProjectChange: (id: number | null) => void;
  onSend: (text: string) => Promise<void>;
  onLoadEvents: (taskId: number) => void;
  onError: (msg: string) => void;
}

export function ChatView(p: Props) {
  const end = useRef<HTMLDivElement>(null);
  const lastTask = p.messages.at(-1)?.task_id;
  const lastStatus = lastTask ? p.tasks[lastTask]?.status : undefined;
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [p.messages.length, lastStatus]);

  const composer = (
    <Composer
      projects={p.projects}
      projectId={p.projectId}
      onProjectChange={p.onProjectChange}
      onSend={p.onSend}
      autoFocus
    />
  );

  if (p.messages.length === 0) {
    return (
      <div className="relative flex h-full flex-col items-center justify-center px-4">
        <div className="dot-grid pointer-events-none absolute inset-0" aria-hidden />
        <div className="relative w-full max-w-2xl">
          <div className="mb-8 flex flex-col items-center gap-5 text-center">
            <DotMatrix text="KOMUTA" dot={5} gap={3} className="max-w-full" />
            <p className="text-[15px] text-dim">Bugün ne inşa ediyoruz?</p>
          </div>
          {composer}
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => void p.onSend(s)}
                className="rounded-full border border-line px-3 py-1.5 text-[12.5px] text-dim transition-colors hover:border-white/30 hover:text-fg"
              >
                {s}
              </button>
            ))}
          </div>
          {p.demoMode && (
            <p className="mt-6 text-center font-mono text-[10.5px] tracking-wider text-faint">
              DEMO MODU · Claude Code yoksa sahte planlar üretilir
            </p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl space-y-5 px-4 py-8">
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
            const t = m.task_id ? p.tasks[m.task_id] : undefined;
            if (t) {
              return (
                <TaskCard
                  key={m.id}
                  task={t}
                  events={p.events[t.id]}
                  onLoadEvents={p.onLoadEvents}
                  onError={p.onError}
                />
              );
            }
            return (
              <div key={m.id} className="whitespace-pre-wrap text-[14.5px] leading-relaxed text-dim">
                {m.content}
              </div>
            );
          })}
          <div ref={end} />
        </div>
      </div>
      <div className="mx-auto w-full max-w-3xl px-4 pb-4">{composer}</div>
    </div>
  );
}
