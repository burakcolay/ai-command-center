import { FileText } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChangesCard } from "../components/ChangesCard";
import { Composer } from "../components/Composer";
import { Orchestra } from "../components/Orchestra";
import { DotMatrix } from "../components/DotMatrix";
import { attachmentUrl, type PendingAttachment } from "../lib/attachments";
import { toolTarget } from "../lib/format";
import type {
  DesignVariant,
  Message,
  ModelChoice,
  Project,
  Task,
  TaskEvent,
  TeamPicture,
} from "../lib/types";

const SUGGESTIONS = [
  "Aklımda bir uygulama fikri var, birlikte netleştirelim",
  "iOS'ta talebi olup rekabeti düşük nişleri araştır",
  "Giriş ekranı için birbirinden farklı 3 tasarım çiz",
  "Bu projede en çok neyi iyileştirmeliyim?",
];

interface Props {
  messages: Message[];
  tasks: Record<number, Task>;
  events: Record<number, TaskEvent[]>;
  activity: Record<number, string>;
  teams: Record<number, TeamPicture>;
  projects: Project[];
  projectId: number | null;
  modelChoice: ModelChoice;
  onModelChoiceChange: (c: ModelChoice) => void;
  demoMode: boolean;
  onProjectChange: (id: number | null) => void;
  onSend: (text: string, attachments: string[]) => Promise<void>;
  onStop: (messageId: number) => void;
  onResume: (messageId: number) => void;
  onLoadEvents: (taskId: number) => void;
  onError: (msg: string) => void;
}

type Prefill = { text: string; nonce: number; attachments?: PendingAttachment[] };

export function ChatView(p: Props) {
  const scroller = useRef<HTMLDivElement>(null);
  const [prefill, setPrefill] = useState<Prefill>();
  const last = p.messages.at(-1);
  const busy = p.messages.find((m) => m.status === "streaming");

  // A chat's changes live in one session; show its card once, under the latest turn that
  // touched it.
  const cardAt = new Map<number, number>(); // message id -> task id
  const seen = new Set<number>();
  for (const m of [...p.messages].reverse()) {
    const taskId = m.meta?.task_id;
    if (taskId && !seen.has(taskId) && p.tasks[taskId]) {
      seen.add(taskId);
      cardAt.set(m.id, taskId);
    }
  }
  const cardKey = [...cardAt.values()].map((id) => `${id}:${p.tasks[id]?.status}`).join();

  // Follow new content, but only if the user hasn't scrolled up to read. Sending a message
  // always jumps to the bottom.
  const sentId = [...p.messages].reverse().find((m) => m.role === "user")?.id;
  const lastSent = useRef(sentId);
  const pinned = useRef(true); // was the view at the bottom before this update?
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const justSent = sentId !== lastSent.current;
    lastSent.current = sentId;
    if (justSent || pinned.current) {
      el.scrollTop = el.scrollHeight;
      pinned.current = true;
    }
  }, [sentId, p.messages.length, last?.content.length, last?.status, cardKey]);

  const ask = (text: string, attachments?: PendingAttachment[]) =>
    setPrefill({ text, nonce: Date.now(), attachments });

  // "Bunu uygula": the chosen design goes along as a reference (PNG + its HTML).
  const applyDesign = (v: DesignVariant) => {
    if (p.projectId === null) p.onError("Projeye uygulamak için aşağıdan bir proje seç.");
    ask(`${v.n}. tasarımı (${v.title}) projeye uygula. Ekteki görseli ve HTML'ini referans al.`, [
      { id: v.attachment, name: v.title, kind: "design", preview: attachmentUrl(v.attachment) },
    ]);
  };

  const composer = (
    <Composer
      projects={p.projects}
      projectId={p.projectId}
      onProjectChange={p.onProjectChange}
      modelChoice={p.modelChoice}
      onModelChoiceChange={p.onModelChoiceChange}
      onSend={p.onSend}
      prefill={prefill}
      onStop={busy ? () => p.onStop(busy.id) : undefined}
      onError={p.onError}
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
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => void p.onSend(s, [])}
                className="rounded-full border border-line px-3 py-1.5 text-[12.5px] text-dim transition-colors hover:border-white/30 hover:text-fg"
              >
                {s}
              </button>
            ))}
          </div>
          <p className="mt-6 text-center text-[12px] leading-relaxed text-faint">
            Ne istediğini düz yaz: sohbet eder, araştırır, tasarım çizer ya da projende değişiklik
            yapar. Değişiklikler sen birleştirene kadar projene dokunmaz.
            {p.demoMode && " · DEMO MODU açık"}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div
        ref={scroller}
        onScroll={(e) => {
          const el = e.currentTarget;
          pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 160;
        }}
        className="flex-1 overflow-y-auto"
      >
        <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-8">
          {p.messages.map((m) => {
            const taskId = cardAt.get(m.id);
            const task = taskId ? p.tasks[taskId] : undefined;
            return (
              <div key={m.id} className="space-y-4">
                {m.role === "user" ? (
                  <UserMessage message={m} />
                ) : m.role === "assistant" ? (
                  <AssistantMessage
                    message={m}
                    activity={p.activity[m.id]}
                    team={p.teams[m.id] ?? m.meta?.team}
                    onApplyDesign={applyDesign}
                    onResume={() => p.onResume(m.id)}
                  />
                ) : (
                  <LegacyTask task={m.task_id ? p.tasks[m.task_id] : undefined} />
                )}
                {task && (
                  <ChangesCard
                    task={task}
                    events={p.events[task.id]}
                    onLoadEvents={p.onLoadEvents}
                    onAsk={(text) => ask(text)}
                    onError={p.onError}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>
      <div className="mx-auto w-full max-w-3xl px-4 pb-4">{composer}</div>
    </div>
  );
}

function UserMessage({ message: m }: { message: Message }) {
  // Newer messages say what each attachment is; older ones only had images.
  const files =
    m.meta?.files ?? (m.meta?.attachments ?? []).map((id) => ({ id, kind: "image", name: "ek" }));
  return (
    <div className="flex justify-end animate-rise">
      <div className="flex max-w-[85%] flex-col items-end gap-2">
        {files.length > 0 && (
          <div className="flex flex-wrap justify-end gap-2">
            {files.map((f) => (
              <a key={f.id} href={attachmentUrl(f.id)} target="_blank" rel="noreferrer">
                {f.kind === "text" ? (
                  <span className="flex items-center gap-2 rounded-xl border border-line-strong px-3 py-2 text-[12.5px] text-dim hover:text-fg">
                    <FileText size={14} /> {f.name}
                  </span>
                ) : (
                  <img
                    src={attachmentUrl(f.id)}
                    alt={f.name}
                    className="max-h-40 rounded-xl border border-line-strong object-cover"
                  />
                )}
              </a>
            ))}
          </div>
        )}
        <div className="whitespace-pre-wrap rounded-2xl rounded-br-sm bg-white/[0.08] px-4 py-2.5 text-[14.5px] leading-relaxed text-fg">
          {m.content}
        </div>
      </div>
    </div>
  );
}

function AssistantMessage({
  message: m,
  activity,
  team,
  onApplyDesign,
  onResume,
}: {
  message: Message;
  activity?: string;
  team?: TeamPicture;
  onApplyDesign: (v: DesignVariant) => void;
  onResume: () => void;
}) {
  const streaming = m.status === "streaming";
  const variants = m.meta?.variants ?? [];
  const reports = m.meta?.reports ?? [];
  const resumeAt = m.meta?.resume_at
    ? new Date(m.meta.resume_at * 1000).toLocaleTimeString("tr-TR", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : null;
  const withTeam = team && team.members.length > 0;
  return (
    <div className="animate-rise">
      {withTeam && <Orchestra team={team} live={streaming} />}
      {m.content && (
        <div className={m.status === "error" ? "md text-danger" : "md"}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
        </div>
      )}
      {variants.length > 0 && (
        <div className="mt-4">
          <DesignGrid variants={variants} onApply={onApplyDesign} />
        </div>
      )}
      {streaming && (
        <div className="mt-2 flex items-center gap-3 font-mono text-[11.5px] text-faint">
          <ScanDots />
          <span className="truncate">{activity ?? (m.content ? "yazıyor" : "düşünüyor")}</span>
        </div>
      )}
      {m.status === "waiting" && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <span className="font-mono text-[11px] text-faint">
            {resumeAt ? `${resumeAt} civarında kendiliğinden devam edecek` : "kota bekleniyor"}
          </span>
          <button
            onClick={onResume}
            className="rounded-full border border-line-strong px-3 py-1 font-mono text-[11px] text-fg transition-colors hover:border-white"
          >
            Şimdi dene
          </button>
        </div>
      )}
      {reports.map((path) => (
        <div
          key={path}
          className="mt-3 flex items-center gap-2 font-mono text-[10.5px] text-faint"
          title={path}
        >
          <FileText size={11} className="shrink-0" />
          <span className="truncate">rapor kaydedildi · {path.split("/").slice(-2).join("/")}</span>
        </div>
      ))}
      {team && !withTeam && !streaming && <Orchestra team={team} live={false} />}
      {m.adapter_id === "ollama" && !streaming && !team && (
        <div className="mt-1.5 font-mono text-[10px] tracking-wide text-faint">yerel model</div>
      )}
    </div>
  );
}

function DesignGrid({
  variants,
  onApply,
}: {
  variants: DesignVariant[];
  onApply: (v: DesignVariant) => void;
}) {
  const wide = variants.some((v) => v.viewport === "desktop");
  return (
    <div className={`grid gap-3 sm:gap-4 ${wide ? "grid-cols-1" : "grid-cols-2 sm:grid-cols-3"}`}>
      {variants.map((v) => (
        <figure key={v.n} className="flex flex-col">
          {v.image ? (
            <a href={v.image} target="_blank" rel="noreferrer" title="Büyük aç">
              <img
                src={v.image}
                alt={v.title}
                className={`w-full border border-line-strong bg-raised object-cover object-top ${
                  v.viewport === "phone" ? "rounded-[22px]" : "rounded-lg"
                }`}
              />
            </a>
          ) : (
            <div className="grid aspect-[393/852] place-items-center rounded-[22px] border border-dashed border-line-strong px-4 text-center text-[12px] text-faint">
              Önizleme oluşturulamadı (Chromium kurulu mu? make setup)
            </div>
          )}
          <figcaption className="mt-2.5">
            <div className="flex items-baseline gap-2">
              <span className="font-mono text-[11px] text-faint">{v.n}</span>
              <span className="text-[14px] font-medium text-fg">{v.title}</span>
            </div>
            {v.idea && <p className="mt-1 text-[12.5px] leading-relaxed text-dim">{v.idea}</p>}
            <button
              onClick={() => onApply(v)}
              className="mt-2 rounded-full border border-line-strong px-3 py-1 font-mono text-[11px] text-fg transition-colors hover:border-white hover:bg-white hover:text-black"
            >
              Bunu uygula
            </button>
          </figcaption>
        </figure>
      ))}
    </div>
  );
}

/** Chats from before the single assistant can still hold old plan tasks. */
function LegacyTask({ task }: { task: Task | undefined }) {
  if (!task) return null;
  return (
    <div className="font-mono text-[10.5px] text-faint">
      eski görev #{task.id} · {task.title}
    </div>
  );
}

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

const AGENT_LABEL: Record<string, string> = {
  arastirmaci: "Araştırmacı",
  tasarimci: "Tasarımcı",
  "test-yazari": "Test yazarı",
  inceleyici: "İnceleyici",
};
const CODEX_TOOL = "mcp__orbit__codex_gorev";

/** "backend-gelistirici" → "Backend geliştirici", "backend-codex" → "Backend (Codex)". */
function agentLabel(name: string): string {
  if (AGENT_LABEL[name]) return AGENT_LABEL[name];
  const cap = (s: string) => s.charAt(0).toLocaleUpperCase("tr") + s.slice(1).replace(/-/g, " ");
  if (name.endsWith("-gelistirici")) return `${cap(name.slice(0, -12))} geliştirici`;
  if (name.endsWith("-codex")) return `${cap(name.slice(0, -6))} (Codex)`;
  return name;
}

/** One live line: who is doing what ("Araştırmacı: rakip fiyatları", "Codex: ▸ Read app.ts"). */
export function activityText(tool: { name: string; input?: unknown; agent?: string }): string {
  const who = tool.agent ? `${agentLabel(tool.agent)}: ` : "";
  if (tool.name === CODEX_TOOL) return `${who}Codex'e görev verdi, Codex çalışıyor`;
  if (tool.name === "Agent" || tool.name === "Task") {
    const i = (tool.input ?? {}) as { description?: string };
    return `${who}${i.description ?? "görev aldı"}`;
  }
  return `${who}▸ ${tool.name} ${toolTarget(tool.input)}`.trim();
}
