import { ArrowUp, FolderKanban } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Project } from "../lib/types";

interface Props {
  projects: Project[];
  projectId: number | null;
  onProjectChange: (id: number | null) => void;
  onSend: (text: string) => Promise<void>;
  autoFocus?: boolean;
}

export function Composer({ projects, projectId, onProjectChange, onSend, autoFocus }: Props) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }, [text]);

  const submit = async () => {
    const t = text.trim();
    if (!t || busy) return;
    setBusy(true);
    try {
      await onSend(t);
      setText("");
    } finally {
      setBusy(false);
      ref.current?.focus();
    }
  };

  return (
    <div className="rounded-2xl border border-line-strong bg-panel/90 backdrop-blur transition-colors focus-within:border-white/40">
      <textarea
        ref={ref}
        value={text}
        autoFocus={autoFocus}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            void submit();
          }
        }}
        rows={1}
        placeholder="Bir görev tanımla…"
        className="block w-full resize-none bg-transparent px-4 pt-4 pb-2 text-[15px] leading-relaxed text-fg placeholder:text-faint focus:outline-none focus-visible:outline-none"
      />
      <div className="flex items-center justify-between gap-3 px-3 pb-3">
        <label className="flex min-w-0 items-center gap-1.5 rounded-md px-1.5 py-1 text-dim hover:text-fg">
          <FolderKanban size={13} strokeWidth={1.6} className="shrink-0" />
          <select
            value={projectId ?? ""}
            onChange={(e) => onProjectChange(e.target.value ? Number(e.target.value) : null)}
            className="min-w-0 max-w-48 cursor-pointer truncate bg-transparent font-mono text-[11px] tracking-wide focus:outline-none"
            aria-label="Proje"
          >
            <option value="" className="bg-panel">
              Proje yok
            </option>
            {projects.map((p) => (
              <option key={p.id} value={p.id} className="bg-panel">
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <button
          onClick={() => void submit()}
          disabled={!text.trim() || busy}
          className="grid size-8 place-items-center rounded-full bg-white text-black transition-opacity disabled:opacity-20"
          aria-label="Gönder"
        >
          <ArrowUp size={16} strokeWidth={2.2} />
        </button>
      </div>
    </div>
  );
}
