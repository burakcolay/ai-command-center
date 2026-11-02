import { X } from "lucide-react";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../lib/api";
import type { Project, ProjectCard } from "../lib/types";

/** The Project Card (PROJE.md): the plan every agent reads before working on the project. */
export function CardViewer({
  project,
  onClose,
  onError,
}: {
  project: Project;
  onClose: () => void;
  onError: (msg: string) => void;
}) {
  const [card, setCard] = useState<ProjectCard | null>(null);

  useEffect(() => {
    api
      .card(project.id)
      .then(setCard)
      .catch((e) => onError(e.message));
  }, [project.id, onError]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4" onClick={onClose}>
      <div
        className="flex h-[min(820px,92vh)] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-line-strong bg-panel"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={`${project.name} proje kartı`}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <div className="text-[15px] font-medium text-fg">{project.name} · Proje Kartı</div>
            <p className="mt-1 text-[12.5px] leading-relaxed text-dim">
              Projenin ortak planı. Lider ve her uzman çalışmadan önce bunu okur; değiştirmek için
              sohbette söylemen yeter.
            </p>
            {card?.state === "pending" && (
              <div className="mt-1.5 font-mono text-[10.5px] text-faint">
                sohbetteki kopyada · henüz projeye birleştirilmedi
              </div>
            )}
          </div>
          <button onClick={onClose} className="text-dim hover:text-fg" aria-label="Kapat">
            <X size={16} />
          </button>
        </div>
        {card && card.team.length > 0 && (
          <div className="flex flex-wrap gap-2 border-b border-line px-5 py-3">
            {card.team.map((a) => (
              <span
                key={a.name}
                className="rounded-md border border-line-strong px-2 py-1 font-mono text-[10.5px] text-dim"
                title={a.tech}
              >
                <span className="text-fg">{a.name}</span> · {a.folder || "-"} ·{" "}
                {a.builder === "codex" ? "Codex" : "Claude"}
              </span>
            ))}
          </div>
        )}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {card === null ? (
            <div className="font-mono text-[11px] text-faint">yükleniyor…</div>
          ) : card.content ? (
            <div className="md">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{card.content}</ReactMarkdown>
            </div>
          ) : (
            <p className="text-[13px] leading-relaxed text-dim">
              Bu projenin henüz bir kartı yok. Sohbete uygulama fikrini ya da bir .md dosyası ver;
              asistan kod yazmadan önce kartı hazırlayıp onayına sunar.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
