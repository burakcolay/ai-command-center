import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Project } from "../lib/types";

/** Edit a project's memory file: lasting decisions and rules every agent sees. */
export function MemoryEditor({
  project,
  onClose,
  onError,
}: {
  project: Project;
  onClose: () => void;
  onError: (msg: string) => void;
}) {
  const [content, setContent] = useState<string | null>(null);
  const [saved, setSaved] = useState("");
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .memory(project.id)
      .then((m) => (setContent(m.content), setSaved(m.content), setPath(m.path)))
      .catch((e) => onError(e.message));
  }, [project.id, onError]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const save = async () => {
    if (content === null) return;
    setBusy(true);
    try {
      const m = await api.saveMemory(project.id, content);
      setSaved(m.content);
      setContent(m.content);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const dirty = content !== null && content !== saved;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4" onClick={onClose}>
      <div
        className="flex h-[min(760px,90vh)] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-line-strong bg-panel"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={`${project.name} proje hafızası`}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <div className="text-[15px] font-medium text-fg">{project.name} · Proje Hafızası</div>
            <p className="mt-1 text-[12.5px] leading-relaxed text-dim">
              Burada yazanlar bu projedeki her sohbete, plana ve ajana verilir. Birleştirilen her
              görev "Karar Günlüğü"ne otomatik eklenir.
            </p>
            <div className="mt-1.5 truncate font-mono text-[10.5px] text-faint" title={path}>
              {path}
            </div>
          </div>
          <button onClick={onClose} className="text-dim hover:text-fg" aria-label="Kapat">
            <X size={16} />
          </button>
        </div>
        <textarea
          value={content ?? "yükleniyor…"}
          disabled={content === null}
          onChange={(e) => setContent(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "s") {
              e.preventDefault();
              void save();
            }
          }}
          spellCheck={false}
          className="flex-1 resize-none bg-ink px-5 py-4 font-mono text-[12.5px] leading-[1.7] text-fg focus:outline-none focus-visible:outline-none"
        />
        <div className="flex items-center justify-between gap-3 border-t border-line px-5 py-3">
          <span className="font-mono text-[10.5px] text-faint">
            {dirty ? "kaydedilmemiş değişiklik · ⌘S" : "kaydedildi"} · Obsidian ile açılabilir düz markdown
          </span>
          <button
            onClick={() => void save()}
            disabled={!dirty || busy}
            className="rounded-lg bg-white px-3.5 py-1.5 text-[13px] font-medium text-black disabled:opacity-30"
          >
            Kaydet
          </button>
        </div>
      </div>
    </div>
  );
}
