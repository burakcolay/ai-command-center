import { BookmarkPlus, MessageCircle, X, Zap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import type { ComposerMode, Template } from "../lib/types";

interface Props {
  query: string;
  active: number;
  currentText: string;
  currentMode: ComposerMode;
  onPick: (t: Template) => void;
  onClose: () => void;
  onItems: (items: Template[]) => void;
  onError: (msg: string) => void;
}

const fold = (s: string) => s.toLocaleLowerCase("tr");

/** Popover above the composer: ready-made and saved requests. */
export function TemplatePicker(p: Props) {
  const [all, setAll] = useState<Template[] | null>(null);
  const [saving, setSaving] = useState(false);
  const [title, setTitle] = useState("");

  const load = () =>
    api
      .templates()
      .then(setAll)
      .catch((e) => p.onError(e.message));

  // Load once when the picker opens.
  useEffect(() => {
    void load();
  }, []);

  const items = useMemo(() => {
    const q = fold(p.query.trim());
    return (all ?? []).filter((t) => !q || fold(`${t.title} ${t.description}`).includes(q));
  }, [all, p.query]);

  const { onItems } = p;
  useEffect(() => onItems(items), [items, onItems]);

  const save = async () => {
    try {
      await api.createTemplate(title.trim(), p.currentText.trim(), p.currentMode);
      setSaving(false);
      setTitle("");
      await load();
    } catch (e) {
      p.onError((e as Error).message);
    }
  };

  const remove = async (t: Template) => {
    try {
      await api.deleteTemplate(t.id);
      await load();
    } catch (e) {
      p.onError((e as Error).message);
    }
  };

  return (
    <div
      className="absolute bottom-full left-0 right-0 z-20 mb-2 overflow-hidden rounded-xl border border-line-strong bg-panel shadow-2xl"
      role="listbox"
      aria-label="Şablonlar"
    >
      <div className="flex items-center justify-between border-b border-line px-3 py-2">
        <span className="label">Şablonlar{p.query ? ` · “${p.query}”` : ""}</span>
        <button onClick={p.onClose} className="text-faint hover:text-fg" aria-label="Kapat">
          <X size={13} />
        </button>
      </div>
      <div className="max-h-72 overflow-y-auto py-1">
        {all === null && <div className="px-3 py-2 font-mono text-[11px] text-faint">yükleniyor…</div>}
        {all !== null && items.length === 0 && (
          <div className="px-3 py-2 text-[12.5px] text-dim">Eşleşen şablon yok.</div>
        )}
        {items.map((t, i) => {
          const Icon = t.mode === "chat" ? MessageCircle : Zap;
          return (
            <div
              key={t.id}
              role="option"
              aria-selected={i === p.active}
              className={`group flex items-center gap-3 px-3 py-2 ${i === p.active ? "bg-white/[0.07]" : "hover:bg-white/[0.04]"}`}
            >
              <button onMouseDown={(e) => e.preventDefault()} onClick={() => p.onPick(t)} className="flex min-w-0 flex-1 items-center gap-3 text-left">
                <Icon size={13} className="shrink-0 text-faint" />
                <span className="shrink-0 text-[13px] text-fg">{t.title}</span>
                <span className="min-w-0 truncate text-[12px] text-faint">{t.description}</span>
              </button>
              {t.custom && (
                <button
                  onClick={() => void remove(t)}
                  className="text-faint opacity-0 hover:text-fg group-hover:opacity-100 focus:opacity-100"
                  aria-label={`${t.title} şablonunu sil`}
                >
                  <X size={12} />
                </button>
              )}
            </div>
          );
        })}
      </div>
      {p.currentText.trim() && !p.currentText.startsWith("/") && (
        <div className="border-t border-line px-3 py-2">
          {saving ? (
            <div className="flex items-center gap-2">
              <input
                autoFocus
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && title.trim()) void save();
                  if (e.key === "Escape") setSaving(false);
                }}
                placeholder="Şablon adı"
                className="min-w-0 flex-1 rounded-md border border-line-strong bg-ink px-2 py-1 text-[12.5px] text-fg focus:border-white/40 focus:outline-none"
              />
              <button
                onClick={() => void save()}
                disabled={!title.trim()}
                className="rounded-md bg-white px-2.5 py-1 text-[12px] font-medium text-black disabled:opacity-30"
              >
                Kaydet
              </button>
            </div>
          ) : (
            <button
              onClick={() => setSaving(true)}
              className="flex items-center gap-1.5 font-mono text-[11px] text-dim hover:text-fg"
            >
              <BookmarkPlus size={12} /> Yazdığını şablon olarak kaydet
            </button>
          )}
        </div>
      )}
    </div>
  );
}
