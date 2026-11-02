import { AlertTriangle, ShieldCheck, Smartphone } from "lucide-react";
import type { TaskPreview } from "../lib/types";

/** The app as it looks right now: built in the sandbox, shown by a browser with no network. */
export function PreviewPanel({
  preview,
  onFix,
  onBuildOutsideSandbox,
}: {
  preview: TaskPreview;
  onFix: (text: string) => void;
  onBuildOutsideSandbox: () => void;
}) {
  const ios = preview.kind === "ios";
  if (preview.status === "running") {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-line px-3 py-2.5 font-mono text-[11px] text-dim">
        <span className="size-1.5 rounded-full bg-white animate-pulse-dot" aria-hidden />
        {ios
          ? "iOS önizlemesi hazırlanıyor · Xcode ile derleniyor, Simülatör'de açılıyor"
          : "önizleme hazırlanıyor · sandbox'ta derleniyor, kilitli tarayıcıda açılıyor"}
      </div>
    );
  }
  if (preview.status === "build_failed") {
    return (
      <div className="overflow-hidden rounded-lg border border-danger/30">
        <div className="flex items-center gap-2 border-b border-danger/30 px-3 py-2 text-[12.5px] text-danger">
          <AlertTriangle size={13} /> Derleme başarısız · <span className="font-mono text-[11px]">{preview.command}</span>
          <span className="ml-auto flex gap-1.5">
            {ios && preview.sandboxed && preview.confirm && (
              <button
                onClick={onBuildOutsideSandbox}
                title="Sandbox derlemeyi engellediyse (ör. GitHub'dan Swift paketi): yalnızca bu sefer, onayınla"
                className="rounded-md border border-line-strong px-2 py-0.5 font-mono text-[11px] text-dim hover:border-white/40 hover:text-fg"
              >
                Sandbox dışında derle
              </button>
            )}
            <button
              onClick={() => onFix("Önizleme derlemesi başarısız oldu, düzelt.")}
              className="rounded-md border border-line-strong px-2 py-0.5 font-mono text-[11px] text-fg hover:border-white/40"
            >
              Düzeltmesini iste
            </button>
          </span>
        </div>
        <pre className="max-h-56 overflow-auto whitespace-pre-wrap bg-ink px-3 py-2 font-mono text-[11px] text-dim">
          {preview.output}
        </pre>
      </div>
    );
  }
  if (preview.status !== "ok") {
    return <p className="font-mono text-[11px] text-faint">Önizleme alınamadı: {preview.reason}</p>;
  }
  const errors = preview.errors ?? [];
  return (
    <div className="overflow-hidden rounded-lg border border-line">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line bg-raised/60 px-3 py-2">
        {ios ? <Smartphone size={12} className="text-dim" /> : <ShieldCheck size={12} className="text-dim" />}
        <span className="font-mono text-[11px] text-fg">{ios ? "iOS önizleme" : "Önizleme"}</span>
        <span className="font-mono text-[10px] text-faint">
          {ios
            ? `${preview.device ?? "iOS Simülatör"} · ${preview.sandboxed ? "sandbox'ta derlendi" : "sandbox dışında derlendi"} · ${preview.seconds} sn`
            : `${preview.build ? `${preview.build} sandbox'ta · ` : ""}ağ kapalı · ${preview.seconds} sn`}
        </span>
        {errors.length > 0 && (
          <button
            onClick={() => onFix("Önizlemedeki tarayıcı hatalarını düzelt.")}
            className="ml-auto rounded-md border border-line-strong px-2 py-0.5 font-mono text-[11px] text-fg hover:border-white/40"
          >
            Hataları düzelttir
          </button>
        )}
      </div>
      <div className="flex gap-3 overflow-x-auto bg-ink p-3">
        {preview.images?.phone && (
          <a href={preview.images.phone} target="_blank" rel="noreferrer" className="shrink-0" title="Telefon">
            <img src={preview.images.phone} alt="Telefon görünümü" className="h-72 rounded-[18px] border border-line-strong" />
          </a>
        )}
        {preview.images?.ios && (
          <a href={preview.images.ios} target="_blank" rel="noreferrer" className="shrink-0" title="iOS Simülatör">
            <img src={preview.images.ios} alt="iOS Simülatör görünümü" className="h-96 rounded-[22px] border border-line-strong" />
          </a>
        )}
        {preview.images?.desktop && (
          <a href={preview.images.desktop} target="_blank" rel="noreferrer" className="shrink-0" title="Masaüstü">
            <img src={preview.images.desktop} alt="Masaüstü görünümü" className="h-72 rounded-lg border border-line-strong" />
          </a>
        )}
      </div>
      {errors.length > 0 && (
        <ul className="border-t border-line px-3 py-2 font-mono text-[10.5px] leading-5 text-danger">
          {errors.map((e) => (
            <li key={e} className="truncate" title={e}>
              {e}
            </li>
          ))}
        </ul>
      )}
      {(preview.blocked?.length ?? 0) > 0 && (
        <div className="border-t border-line px-3 py-1.5 font-mono text-[10px] text-faint">
          engellenen dış istekler: {preview.blocked!.length} (önizlemede internet yok)
        </div>
      )}
    </div>
  );
}
