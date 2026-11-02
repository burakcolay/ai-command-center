import { Check, ChevronRight, Minus, ShieldCheck, X } from "lucide-react";
import { useState } from "react";
import type { CheckResult } from "../lib/types";

/** Quality-gate results: measured by Orbit in the sandbox, not reported by the assistant. */
export function ChecksPanel({
  results,
  onFix,
  onRerun,
  busy,
}: {
  results: CheckResult[];
  onFix?: () => void;
  onRerun?: () => void;
  busy?: boolean;
}) {
  const failed = results.filter((r) => r.status === "failed").length;
  const passed = results.filter((r) => r.status === "passed").length;
  return (
    <div className="overflow-hidden rounded-lg border border-line">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line bg-raised/60 px-3 py-2">
        <ShieldCheck size={12} className="text-dim" />
        <span className="font-mono text-[11px] text-fg">Kalite kontrolleri</span>
        <span className={`font-mono text-[11px] ${failed ? "text-danger" : "text-dim"}`}>
          {passed} geçti{failed ? ` · ${failed} başarısız` : ""}
        </span>
        <span className="font-mono text-[10px] text-faint">sandbox'ta ölçüldü</span>
        {onRerun && (
          <button
            onClick={onRerun}
            disabled={busy}
            className="ml-auto font-mono text-[11px] text-dim hover:text-fg disabled:opacity-30"
            title="Asistanı çalıştırmadan kontrolleri tekrar çalıştır (ör. kontrol ayarını değiştirdikten sonra)"
          >
            Yeniden çalıştır
          </button>
        )}
        {failed > 0 && onFix && (
          <button
            onClick={onFix}
            disabled={busy}
            className="rounded-md border border-line-strong px-2.5 py-0.5 font-mono text-[11px] text-fg hover:border-white/40 disabled:opacity-30"
            title="Asistandan düzeltmesini iste; hata çıktısını kendisi görür"
          >
            Düzeltmesini iste
          </button>
        )}
      </div>
      {results.map((r, i) => (
        <CheckRow key={`${r.name}-${i}`} result={r} />
      ))}
    </div>
  );
}

function CheckRow({ result: r }: { result: CheckResult }) {
  const [open, setOpen] = useState(r.status === "failed");
  const Icon = r.status === "passed" ? Check : r.status === "failed" ? X : Minus;
  return (
    <div className="border-b border-line last:border-b-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2.5 px-3 py-1.5 text-left hover:bg-white/[0.03]"
        aria-expanded={open}
      >
        <Icon
          size={13}
          className={r.status === "failed" ? "text-danger" : r.status === "passed" ? "text-fg" : "text-faint"}
        />
        <span className="text-[13px] text-fg">{r.name}</span>
        <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-faint">{r.command}</span>
        {r.timed_out && <span className="font-mono text-[10.5px] text-danger">zaman aşımı</span>}
        {r.duration_ms != null && (
          <span className="font-mono text-[10.5px] text-faint">{(r.duration_ms / 1000).toFixed(1)} sn</span>
        )}
        <ChevronRight size={12} className={`text-faint transition-transform ${open ? "rotate-90" : ""}`} />
      </button>
      {open && r.output && (
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap bg-ink px-3 py-2 font-mono text-[11px] leading-[17px] text-dim">
          {r.output}
        </pre>
      )}
    </div>
  );
}
