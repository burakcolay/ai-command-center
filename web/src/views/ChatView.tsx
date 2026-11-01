import { Palette, Telescope, Zap } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Composer } from "../components/Composer";
import { DotMatrix } from "../components/DotMatrix";
import { TaskCard } from "../components/TaskCard";
import { attachmentUrl, type PendingAttachment } from "../lib/attachments";
import { toolTarget } from "../lib/format";
import type { ComposerMode, DesignVariant, Message, Project, Task, TaskEvent } from "../lib/types";

const SUGGESTIONS: Record<ComposerMode, string[]> = {
  research: [
    "Global bir iOS uygulaması için talebi yüksek, rekabeti düşük nişleri araştır",
    "Habit tracker uygulamalarının en büyük kullanıcı şikayetleri neler?",
  ],
  chat: [
    "Aklımda bir uygulama fikri var, birlikte netleştirelim",
    "Bu projenin mimarisini bana anlat",
    "Bu projede en çok neyi iyileştirmeliyim?",
  ],
  design: [
    "Giriş ekranı için birbirinden farklı 3 tasarım",
    "Ayarlar sayfasını daha sade gösteren 2 alternatif",
  ],
  edit: [
    "Ana ekrandaki başlığı daha büyük ve kalın yap",
    "Hata mesajlarını Türkçeleştir",
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
  chatModels: { id: string | null; label: string }[];
  chatModel: string | null;
  onChatModelChange: (id: string | null) => void;
  demoMode: boolean;
  onModeChange: (m: ComposerMode) => void;
  onProjectChange: (id: number | null) => void;
  onSend: (text: string, attachments: string[]) => Promise<void>;
  onStop: (messageId: number) => void;
  onLoadEvents: (taskId: number) => void;
  onError: (msg: string) => void;
}

export function ChatView(p: Props) {
  const scroller = useRef<HTMLDivElement>(null);
  const [prefill, setPrefill] = useState<{
    text: string;
    nonce: number;
    attachments?: PendingAttachment[];
  }>();
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

  // "Bunu uygula": the chosen design goes to an edit session as a reference (PNG + HTML).
  const applyDesign = (v: DesignVariant) => {
    p.onModeChange("edit");
    setPrefill({
      text: `Tasarım ${v.n}'i (${v.title}) projede uygula. Ekteki görseli ve HTML'ini referans al.`,
      nonce: Date.now(),
      attachments: [{ id: v.attachment, name: v.title, preview: attachmentUrl(v.attachment) }],
    });
  };

  const composer = (
    <Composer
      projects={p.projects}
      projectId={p.projectId}
      onProjectChange={p.onProjectChange}
      mode={p.mode}
      onModeChange={p.onModeChange}
      chatModels={p.chatModels}
      chatModel={p.chatModel}
      onChatModelChange={p.onChatModelChange}
      onSend={p.onSend}
      prefill={prefill}
      onStop={streaming ? () => p.onStop(streaming.id) : undefined}
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
            {SUGGESTIONS[p.mode].map((s) => (
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
            {
              {
                chat: "Sohbet modunda hiçbir dosya değişmez. Karar verdiğinde sohbeti göreve dönüştür.",
                research:
                  "Araştırma modu onlarca kaynak tarar, kaynakçalı bir rapor yazar ve kaydeder. Birkaç dakika sürebilir.",
                edit: "Düzenle modunda her mesaj hemen uygulanır (projenin bir kopyasında). Diff'i görüp birleştirirsin.",
                design:
                  "Tasarım modu 2-3 farklı ekran çizer ve görsellerini yan yana gösterir. Beğendiğini uygulatırsın.",
                task: "Görev modunda Orchestrator bir plan çıkarır; onayından sonra ajanlar uygular.",
              }[p.mode]
            }
            {p.demoMode && " · DEMO MODU açık"}
          </p>
        </div>
      </div>
    );
  }

  const lastAssistant = [...p.messages].reverse().find((m) => m.role === "assistant");
  // A session collects many messages; its card is shown once, at its latest message.
  const lastCardFor = new Map<number, number>();
  for (const m of p.messages) if (m.role === "task" && m.task_id) lastCardFor.set(m.task_id, m.id);

  return (
    <div className="flex h-full flex-col">
      <div ref={scroller} className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-8">
          {p.messages.map((m) => {
            if (m.role === "user") {
              return (
                <div key={m.id} className="flex justify-end animate-rise">
                  <div className="flex max-w-[85%] flex-col items-end gap-2">
                    {m.meta?.attachments && m.meta.attachments.length > 0 && (
                      <div className="flex flex-wrap justify-end gap-2">
                        {m.meta.attachments.map((id) => (
                          <a key={id} href={attachmentUrl(id)} target="_blank" rel="noreferrer">
                            <img
                              src={attachmentUrl(id)}
                              alt="ek"
                              className="max-h-40 rounded-xl border border-line-strong object-cover"
                            />
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
            if (m.role === "task") {
              const t = m.task_id ? p.tasks[m.task_id] : undefined;
              if (t && lastCardFor.get(t.id) !== m.id) {
                return (
                  <div key={m.id} className="font-mono text-[10.5px] text-faint">
                    ↳ düzenleme oturumuna eklendi · #{t.id}
                  </div>
                );
              }
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
                onApplyDesign={applyDesign}
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
  onApplyDesign,
}: {
  message: Message;
  activity?: string;
  canConvert: boolean;
  onConvert: () => void;
  onApplyDesign: (v: DesignVariant) => void;
}) {
  const streaming = m.status === "streaming";
  const research = m.meta?.kind === "research";
  const design = m.meta?.kind === "design";
  const variants = m.meta?.variants;
  const report = m.meta?.report_path;
  return (
    <div className="animate-rise">
      {research && (
        <div className="mb-2 flex items-center gap-2 font-mono text-[10.5px] tracking-[0.14em] text-faint">
          <Telescope size={11} /> ARAŞTIRMA RAPORU
        </div>
      )}
      {design && (
        <div className="mb-3 flex items-center gap-2 font-mono text-[10.5px] tracking-[0.14em] text-faint">
          <Palette size={11} /> TASARIM ÖNERİLERİ
        </div>
      )}
      {variants && variants.length > 0 ? (
        <DesignGrid variants={variants} wide={m.meta?.viewport === "desktop"} onApply={onApplyDesign} />
      ) : m.content ? (
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
          <span className="truncate">
            {activity ??
              (m.content
                ? "yazıyor"
                : research
                  ? "kaynaklar taranıyor"
                  : design
                    ? "tasarımlar çiziliyor"
                    : "düşünüyor")}
          </span>
        </div>
      )}
      {report && !streaming && (
        <div className="mt-2 truncate font-mono text-[10.5px] text-faint" title={report}>
          kaydedildi · {report.split("/").slice(-2).join("/")}
        </div>
      )}
      {m.adapter_id === "ollama" && !streaming && (
        <div className="mt-1.5 font-mono text-[10px] tracking-wide text-faint">yerel model</div>
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

function DesignGrid({
  variants,
  wide,
  onApply,
}: {
  variants: DesignVariant[];
  wide: boolean;
  onApply: (v: DesignVariant) => void;
}) {
  return (
    <div className={`grid gap-4 ${wide ? "grid-cols-1" : "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"}`}>
      {variants.map((v) => (
        <figure key={v.n} className="flex flex-col">
          {v.image ? (
            <a href={v.image} target="_blank" rel="noreferrer" title="Büyük aç">
              <img
                src={v.image}
                alt={v.title}
                className={`w-full border border-line-strong bg-raised object-cover object-top ${
                  wide ? "rounded-lg" : "rounded-[22px]"
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
            <p className="mt-1 text-[12.5px] leading-relaxed text-dim">{v.idea}</p>
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

export function activityText(tool: { name: string; input?: unknown }): string {
  return `▸ ${tool.name} ${toolTarget(tool.input)}`.trim();
}
