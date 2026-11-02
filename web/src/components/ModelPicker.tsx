import { Check, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { CatalogModel, CatalogProvider } from "../lib/types";

const EFFORT_HINT: Record<string, string> = {
  low: "hızlı, az token",
  medium: "dengeli",
  high: "derin düşünür",
  xhigh: "çok derin",
  max: "en derin; kotayı hızlı bitirir",
  ultra: "en derin + kendi kendine iş böler",
};

export function pickLabel(
  catalog: CatalogProvider[] | null,
  choice: string,
  effort: string | null,
): string {
  if (choice === "auto") return "Otomatik";
  const [provider, ...rest] = choice.split("/");
  const id = rest.join("/");
  const model = catalog?.find((p) => p.id === provider)?.models.find((m) => m.id === id);
  return `${model?.label ?? (id || choice)}${effort ? ` · ${effort}` : ""}`;
}

/** Pick Otomatik, or any provider's model and how hard it thinks. */
export function ModelPicker({
  choice,
  effort,
  onChange,
  onClose,
  onError,
}: {
  choice: string;
  effort: string | null;
  onChange: (choice: string, effort: string | null) => void;
  onClose: () => void;
  onError: (msg: string) => void;
}) {
  const [catalog, setCatalog] = useState<CatalogProvider[] | null>(null);

  useEffect(() => {
    api
      .catalog()
      .then(setCatalog)
      .catch((e) => onError(e.message));
  }, [onError]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const pick = (provider: CatalogProvider, model: CatalogModel) => {
    const keep = effort && model.efforts.includes(effort) ? effort : model.effort || null;
    onChange(`${provider.id}/${model.id}`, keep);
  };

  return (
    <div
      className="absolute bottom-full left-0 right-0 z-20 mb-2 max-h-[min(460px,45vh)] overflow-y-auto rounded-xl border border-line-strong bg-panel shadow-2xl"
      role="dialog"
      aria-label="Model seç"
    >
      <div className="sticky top-0 flex items-center justify-between border-b border-line bg-panel px-3 py-2">
        <span className="label">Model ve efor</span>
        <button onClick={onClose} className="text-faint hover:text-fg" aria-label="Kapat">
          <X size={13} />
        </button>
      </div>
      <button
        onClick={() => onChange("auto", null)}
        className={`flex w-full items-start gap-2.5 px-3 py-2.5 text-left hover:bg-white/[0.04] ${
          choice === "auto" ? "bg-white/[0.06]" : ""
        }`}
      >
        <span className="mt-0.5 w-3">{choice === "auto" && <Check size={12} />}</span>
        <span>
          <span className="text-[13px] text-fg">Otomatik</span>
          <span className="block text-[11.5px] text-faint">
            Sohbet hafif modelle, gerçek iş kalite planındaki ekiple. Önerilen.
          </span>
        </span>
      </button>
      {catalog === null && <div className="px-3 py-2 font-mono text-[11px] text-faint">yükleniyor…</div>}
      {catalog?.map((p) => (
        <div key={p.id} className={`border-t border-line ${p.available ? "" : "opacity-50"}`}>
          <div className="px-3 pt-2.5">
            <div className="flex items-baseline gap-2">
              <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-dim">{p.name}</span>
              <span className="text-[11px] text-faint">{p.note}</span>
            </div>
            {!p.available && <div className="text-[11px] text-faint">{p.reason}</div>}
          </div>
          <div className="py-1">
            {p.models.length === 0 && p.available && (
              <div className="px-3 py-1 text-[11.5px] text-faint">Model listesi alınamadı.</div>
            )}
            {p.models.map((m) => {
              const selected = choice === `${p.id}/${m.id}`;
              return (
                <div key={m.id} className={selected ? "bg-white/[0.06]" : ""}>
                  <button
                    disabled={!p.available}
                    onClick={() => pick(p, m)}
                    className="flex w-full items-center gap-2.5 px-3 py-1.5 text-left hover:bg-white/[0.04] disabled:cursor-not-allowed"
                  >
                    <span className="w-3">{selected && <Check size={12} />}</span>
                    <span className="text-[13px] text-fg">{m.label}</span>
                    {m.note && <span className="min-w-0 truncate text-[11px] text-faint">{m.note}</span>}
                  </button>
                  {selected && m.efforts.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 px-3 pb-2 pl-[34px]" role="group" aria-label="Efor">
                      {m.efforts.map((e) => (
                        <button
                          key={e}
                          onClick={() => onChange(`${p.id}/${m.id}`, e)}
                          title={EFFORT_HINT[e] ?? e}
                          aria-pressed={effort === e}
                          className={`rounded-full border px-2.5 py-0.5 font-mono text-[10.5px] transition-colors ${
                            effort === e
                              ? "border-white bg-white text-black"
                              : "border-line-strong text-dim hover:border-white/40 hover:text-fg"
                          }`}
                        >
                          {e}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
