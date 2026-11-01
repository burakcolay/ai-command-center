import {
  ArrowUp,
  Cpu,
  FolderKanban,
  LayoutTemplate,
  MessageCircle,
  Palette,
  Paperclip,
  PenLine,
  Square,
  Telescope,
  X,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { type PendingAttachment, uploadImage } from "../lib/attachments";
import type { ComposerMode, Project, Template } from "../lib/types";
import { TemplatePicker } from "./TemplatePicker";

interface Props {
  projects: Project[];
  projectId: number | null;
  onProjectChange: (id: number | null) => void;
  mode: ComposerMode;
  onModeChange: (m: ComposerMode) => void;
  /** Models that can answer in chat mode; id null = default (Claude). */
  chatModels: { id: string | null; label: string }[];
  chatModel: string | null;
  onChatModelChange: (id: string | null) => void;
  onSend: (text: string, attachments: string[]) => Promise<void>;
  /** Set from outside (e.g. "Göreve dönüştür", "Bunu uygula"); `nonce` makes repeats apply. */
  prefill?: { text: string; nonce: number; attachments?: PendingAttachment[] };
  /** While a reply is streaming: show a stop button instead of send. */
  onStop?: () => void;
  onError: (msg: string) => void;
  autoFocus?: boolean;
}

/** Select the first [placeholder] so the user can type over it right away. */
function selectPlaceholder(el: HTMLTextAreaElement) {
  const start = el.value.indexOf("[");
  const end = start === -1 ? -1 : el.value.indexOf("]", start);
  if (end > start) el.setSelectionRange(start, end + 1);
  else el.setSelectionRange(el.value.length, el.value.length);
}

const PLACEHOLDER: Record<ComposerMode, string> = {
  chat: "Bir şey sor ya da fikrini anlat…",
  research: "Ne araştırılsın? ör. iOS'ta talebi olup rekabeti düşük nişler",
  design: "Hangi ekran? ör. giriş ekranı için 3 farklı fikir (ekran görüntüsü ekleyebilirsin)",
  edit: "Ne değişsin? ör. giriş butonunu büyüt, rengini koyulaştır",
  task: "Yapılacak işi tanımla — plan çıkarılıp onayına sunulur…",
};

export function Composer(p: Props) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [files, setFiles] = useState<PendingAttachment[]>([]);
  const [uploading, setUploading] = useState(0);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const [picker, setPicker] = useState(false);
  const [active, setActive] = useState(0);
  const items = useRef<Template[]>([]);
  const ref = useRef<HTMLTextAreaElement>(null);
  // "/" at the very start opens the picker and filters it as you type.
  const slash = /^\/[^\s]*$/.test(text);
  const pickerOpen = picker || slash;
  const onItems = useCallback((list: Template[]) => {
    items.current = list;
    setActive((a) => Math.min(a, Math.max(list.length - 1, 0)));
  }, []);

  const pick = (t: Template) => {
    setText(t.body);
    p.onModeChange(t.mode);
    setPicker(false);
    setActive(0);
    requestAnimationFrame(() => {
      const el = ref.current;
      if (!el) return;
      el.focus();
      selectPlaceholder(el);
    });
  };

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }, [text]);

  const addFiles = async (list: FileList | File[]) => {
    const images = Array.from(list).filter((f) => f.type.startsWith("image/"));
    for (const file of images.slice(0, 6 - files.length)) {
      setUploading((n) => n + 1);
      try {
        const a = await uploadImage(file);
        setFiles((prev) => [...prev, a]);
      } catch (e) {
        p.onError((e as Error).message);
      } finally {
        setUploading((n) => n - 1);
      }
    }
  };

  useEffect(() => {
    if (!p.prefill) return;
    setText(p.prefill.text);
    if (p.prefill.attachments) setFiles(p.prefill.attachments);
    requestAnimationFrame(() => {
      const el = ref.current;
      el?.focus();
      el?.setSelectionRange(el.value.length, el.value.length);
    });
  }, [p.prefill]);

  const submit = async () => {
    const t = text.trim();
    if (!t || busy || uploading || p.onStop) return;
    setBusy(true);
    try {
      await p.onSend(
        t,
        files.map((f) => f.id),
      );
      setText("");
      setFiles([]);
    } finally {
      setBusy(false);
      ref.current?.focus();
    }
  };

  return (
    <div
      className={`relative rounded-2xl border bg-panel/90 backdrop-blur transition-colors focus-within:border-white/40 ${
        dragging ? "border-white" : p.mode === "task" ? "border-white/30" : "border-line-strong"
      }`}
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes("Files")) {
          e.preventDefault();
          setDragging(true);
        }
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        void addFiles(e.dataTransfer.files);
      }}
    >
      {pickerOpen && (
        <TemplatePicker
          query={slash ? text.slice(1) : ""}
          active={active}
          currentText={text}
          currentMode={p.mode}
          onPick={pick}
          onClose={() => {
            setPicker(false);
            if (slash) setText("");
          }}
          onItems={onItems}
          onError={p.onError}
        />
      )}
      {(files.length > 0 || uploading > 0) && (
        <div className="flex flex-wrap gap-2 px-3 pt-3">
          {files.map((f) => (
            <div key={f.id} className="group relative">
              <img
                src={f.preview}
                alt={f.name}
                className="size-14 rounded-lg border border-line-strong object-cover"
              />
              <button
                onClick={() => setFiles((prev) => prev.filter((x) => x.id !== f.id))}
                className="absolute -right-1.5 -top-1.5 grid size-5 place-items-center rounded-full border border-line-strong bg-panel text-dim hover:text-fg"
                aria-label={`${f.name} ekini kaldır`}
              >
                <X size={11} />
              </button>
            </div>
          ))}
          {uploading > 0 && (
            <div className="grid size-14 place-items-center rounded-lg border border-dashed border-line-strong font-mono text-[10px] text-faint">
              yükleniyor
            </div>
          )}
        </div>
      )}
      <textarea
        ref={ref}
        value={text}
        autoFocus={p.autoFocus}
        onPaste={(e) => {
          if (e.clipboardData.files.length) {
            e.preventDefault();
            void addFiles(e.clipboardData.files);
          }
        }}
        onChange={(e) => {
          setText(e.target.value);
          setActive(0);
        }}
        onKeyDown={(e) => {
          if (pickerOpen && items.current.length) {
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
              e.preventDefault();
              const n = items.current.length;
              setActive((a) => (a + (e.key === "ArrowDown" ? 1 : n - 1)) % n);
              return;
            }
            if (e.key === "Enter" && slash) {
              e.preventDefault();
              pick(items.current[active]);
              return;
            }
          }
          if (e.key === "Escape" && pickerOpen) {
            setPicker(false);
            if (slash) setText("");
            return;
          }
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
          <input
            ref={fileInput}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            multiple
            hidden
            onChange={(e) => {
              if (e.target.files) void addFiles(e.target.files);
              e.target.value = "";
            }}
          />
          <button
            type="button"
            onClick={() => fileInput.current?.click()}
            title="Görsel ekle (ya da yapıştır / sürükle)"
            aria-label="Görsel ekle"
            className="grid size-7 shrink-0 place-items-center rounded-md text-dim transition-colors hover:text-fg"
          >
            <Paperclip size={14} strokeWidth={1.6} />
          </button>
          <button
            type="button"
            onClick={() => setPicker((o) => !o)}
            aria-expanded={pickerOpen}
            title="Şablonlar (veya kutunun başına / yaz)"
            className={`grid size-7 shrink-0 place-items-center rounded-md transition-colors ${
              pickerOpen ? "bg-white/[0.08] text-fg" : "text-dim hover:text-fg"
            }`}
          >
            <LayoutTemplate size={14} strokeWidth={1.6} />
          </button>
          {p.mode === "chat" && p.chatModels.length > 1 && (
            <label
              className="flex min-w-0 items-center gap-1.5 rounded-md px-1.5 py-1 text-dim hover:text-fg"
              title="Yanıtı hangi model versin? Yerel model proje dosyalarını okuyamaz."
            >
              <Cpu size={13} strokeWidth={1.6} className="shrink-0" />
              <select
                value={p.chatModel ?? ""}
                onChange={(e) => p.onChatModelChange(e.target.value || null)}
                className="min-w-0 max-w-48 cursor-pointer truncate bg-transparent font-mono text-[11px] tracking-wide focus:outline-none"
                aria-label="Model"
              >
                {p.chatModels.map((m) => (
                  <option key={m.id ?? ""} value={m.id ?? ""} className="bg-panel">
                    {m.label}
                  </option>
                ))}
              </select>
            </label>
          )}
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
            disabled={!text.trim() || busy || uploading > 0}
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
  // Only the active mode shows its label; the others are icons with a tooltip.
  const item = (m: ComposerMode, label: string, Icon: typeof Zap, hint: string) => (
    <button
      type="button"
      onClick={() => onChange(m)}
      aria-pressed={mode === m}
      aria-label={label}
      title={`${label} — ${hint}`}
      className={`flex items-center gap-1.5 rounded-full py-1 font-mono text-[11px] tracking-wide transition-colors ${
        mode === m ? "bg-white px-2.5 text-black" : "px-2 text-dim hover:text-fg"
      }`}
    >
      <Icon size={12} strokeWidth={2} />
      {mode === m && label}
    </button>
  );
  return (
    <div className="flex shrink-0 items-center rounded-full border border-line p-0.5" role="group" aria-label="Mod">
      {item("chat", "Sohbet", MessageCircle, "Konuş, fikirleri netleştir. Hiçbir dosya değişmez.")}
      {item(
        "research",
        "Araştırma",
        Telescope,
        "Onlarca kaynak tarar, kaynakçalı rapor yazar ve kaydeder. Birkaç dakika sürebilir.",
      )}
      {item(
        "design",
        "Tasarım",
        Palette,
        "Bir ekran için 2-3 farklı tasarım çizer ve görsellerini yan yana gösterir.",
      )}
      {item(
        "edit",
        "Düzenle",
        PenLine,
        "Küçük değişiklikler: plan yok, hemen uygulanır; diff'i görüp birleştirirsin.",
      )}
      {item("task", "Görev", Zap, "Plan çıkar, onayla, ajanlar uygulasın.")}
    </div>
  );
}
