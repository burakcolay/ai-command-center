import { ArrowUp, FolderKanban, MessageCircle, Square, Zap } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { ComposerMode, Project } from "../lib/types";

interface Props {
  projects: Project[];
  projectId: number | null;
  onProjectChange: (id: number | null) => void;
  mode: ComposerMode;
  onModeChange: (m: ComposerMode) => void;
  onSend: (text: string) => Promise<void>;
  /** Set from outside (e.g. "Göreve dönüştür"); `nonce` makes repeated prefills apply. */
  prefill?: { text: string; nonce: number };
  /** While a reply is streaming: show a stop button instead of send. */
  onStop?: () => void;
  autoFocus?: boolean;
}

const PLACEHOLDER: Record<ComposerMode, string> = {
  chat: "Bir şey sor ya da fikrini anlat…",
  task: "Yapılacak işi tanımla — plan çıkarılıp onayına sunulur…",
};

export function Composer(p: Props) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }, [text]);

  useEffect(() => {
    if (!p.prefill) return;
    setText(p.prefill.text);
    requestAnimationFrame(() => {
      const el = ref.current;
      el?.focus();
      el?.setSelectionRange(el.value.length, el.value.length);
    });
  }, [p.prefill]);

  const submit = async () => {
    const t = text.trim();
    if (!t || busy || p.onStop) return;
    setBusy(true);
    try {
      await p.onSend(t);
      setText("");
    } finally {
      setBusy(false);
      ref.current?.focus();
    }
  };

  return (
    <div
      className={`rounded-2xl border bg-panel/90 backdrop-blur transition-colors focus-within:border-white/40 ${
        p.mode === "task" ? "border-white/30" : "border-line-strong"
      }`}
    >
      <textarea
        ref={ref}
        value={text}
        autoFocus={p.autoFocus}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            void submit();
          }
        }}
        rows={1}
        placeholder={PLACEHOLDER[p.mode]}
        className="block w-full resize-none bg-transparent px-4 pt-4 pb-2 text-[15px] leading-relaxed text-fg placeholder:text-faint focus:outline-none focus-visible:outline-none"
      />
      <div className="flex items-center justify-between gap-2 px-3 pb-3">
        <div className="flex min-w-0 items-center gap-1">
          <ModeSwitch mode={p.mode} onChange={p.onModeChange} />
          <label className="flex min-w-0 items-center gap-1.5 rounded-md px-1.5 py-1 text-dim hover:text-fg">
            <FolderKanban size={13} strokeWidth={1.6} className="shrink-0" />
            <select
              value={p.projectId ?? ""}
              onChange={(e) => p.onProjectChange(e.target.value ? Number(e.target.value) : null)}
              className="min-w-0 max-w-40 cursor-pointer truncate bg-transparent font-mono text-[11px] tracking-wide focus:outline-none"
              aria-label="Proje"
            >
              <option value="" className="bg-panel">
                Proje yok
              </option>
              {p.projects.map((pr) => (
                <option key={pr.id} value={pr.id} className="bg-panel">
                  {pr.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        {p.onStop ? (
          <button
            onClick={p.onStop}
            className="grid size-8 shrink-0 place-items-center rounded-full border border-white/50 text-fg hover:bg-white hover:text-black"
            aria-label="Yanıtı durdur"
            title="Yanıtı durdur"
          >
            <Square size={11} fill="currentColor" />
          </button>
        ) : (
          <button
            onClick={() => void submit()}
            disabled={!text.trim() || busy}
            className="grid size-8 shrink-0 place-items-center rounded-full bg-white text-black transition-opacity disabled:opacity-20"
            aria-label={p.mode === "task" ? "Görevi gönder" : "Gönder"}
          >
            <ArrowUp size={16} strokeWidth={2.2} />
          </button>
        )}
      </div>
    </div>
  );
}

function ModeSwitch({ mode, onChange }: { mode: ComposerMode; onChange: (m: ComposerMode) => void }) {
  const item = (m: ComposerMode, label: string, Icon: typeof Zap, hint: string) => (
    <button
      type="button"
      onClick={() => onChange(m)}
      aria-pressed={mode === m}
      title={hint}
      className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-[11px] tracking-wide transition-colors ${
        mode === m ? "bg-white text-black" : "text-dim hover:text-fg"
      }`}
    >
      <Icon size={12} strokeWidth={2} />
      {label}
    </button>
  );
  return (
    <div className="flex shrink-0 items-center rounded-full border border-line p-0.5" role="group" aria-label="Mod">
      {item("chat", "Sohbet", MessageCircle, "Konuş, fikirleri netleştir. Hiçbir dosya değişmez.")}
      {item("task", "Görev", Zap, "Plan çıkar, onayla, ajanlar uygulasın.")}
    </div>
  );
}
