import { ChevronRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import type { DiffFile, TaskDiff } from "../lib/types";

/** Read-only review of the task branch against its base. Reloads when `version` changes. */
export function DiffView({ taskId, version }: { taskId: number; version: string }) {
  const [diff, setDiff] = useState<TaskDiff | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .diff(taskId)
      .then((d) => alive && (setDiff(d), setError(null)))
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [taskId, version]);

  const patches = useMemo(() => splitPatch(diff?.patch ?? ""), [diff]);

  if (error) return <p className="text-[12.5px] text-dim">{error}</p>;
  if (!diff) return <p className="font-mono text-[11px] text-faint">değişiklikler yükleniyor…</p>;

  const added = diff.files.reduce((n, f) => n + f.added, 0);
  const removed = diff.files.reduce((n, f) => n + f.removed, 0);

  return (
    <div className="overflow-hidden rounded-lg border border-line">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line bg-raised/60 px-3 py-2 font-mono text-[11px]">
        <span className="text-fg">{diff.files.length} dosya</span>
        <span className="text-fg">+{added}</span>
        <span className="text-dim">−{removed}</span>
        {diff.truncated && <span className="text-faint">çok büyük; kısaltıldı</span>}
      </div>
      {diff.files.map((f) => (
        <FileDiff key={f.path} file={f} patch={patches[f.path]} defaultOpen={diff.files.length <= 4} />
      ))}
    </div>
  );
}

function FileDiff({ file, patch, defaultOpen }: { file: DiffFile; patch?: string[]; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen && !file.binary);
  return (
    <div className="border-b border-line last:border-b-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-white/[0.03]"
        aria-expanded={open}
      >
        <ChevronRight size={12} className={`shrink-0 text-faint transition-transform ${open ? "rotate-90" : ""}`} />
        <span className="min-w-0 flex-1 truncate font-mono text-[12px] text-fg">{file.path}</span>
        {file.binary ? (
          <span className="font-mono text-[10.5px] text-faint">ikili dosya</span>
        ) : (
          <span className="flex gap-2 font-mono text-[10.5px]">
            <span className="text-fg">+{file.added}</span>
            <span className="text-dim">−{file.removed}</span>
          </span>
        )}
      </button>
      {open && patch && (
        <pre className="max-h-96 overflow-auto bg-ink py-1 font-mono text-[11.5px] leading-[18px]">
          {patch.map((line, i) => (
            <div key={i} className={lineClass(line)}>
              {line || " "}
            </div>
          ))}
        </pre>
      )}
    </div>
  );
}

function lineClass(line: string): string {
  const base = "px-3 whitespace-pre";
  if (line.startsWith("@@")) return `${base} text-faint`;
  if (line.startsWith("+")) return `${base} bg-white/[0.07] text-fg`;
  if (line.startsWith("-")) return `${base} text-faint`;
  return `${base} text-dim`;
}

/** Split a unified diff into hunk lines per file path (headers dropped). */
function splitPatch(patch: string): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const chunk of patch.split(/^diff --git /m).slice(1)) {
    const lines = chunk.split("\n");
    const plus = lines.find((l) => l.startsWith("+++ "));
    const minus = lines.find((l) => l.startsWith("--- "));
    const rename = lines.find((l) => l.startsWith("rename to "));
    const path =
      rename?.slice(10) ??
      (plus && plus !== "+++ /dev/null" ? plus.slice(6) : minus?.slice(6)) ??
      lines[0].split(" b/").at(-1) ??
      "";
    const start = lines.findIndex((l) => l.startsWith("@@"));
    out[path] = start === -1 ? [] : lines.slice(start).filter((l, i, a) => i < a.length - 1 || l);
  }
  return out;
}
