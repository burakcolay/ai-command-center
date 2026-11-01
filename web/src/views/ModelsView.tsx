import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import { ModelDot } from "../components/StatusDot";
import { BILLING_LABEL, MODEL_STATE_LABEL, USAGE_SOURCE_LABEL, WINDOW_LABEL } from "../lib/labels";
import type { ModelInfo } from "../lib/types";
import { Page } from "./Page";

const CAP_LABEL: Record<string, string> = {
  chat: "Sohbet",
  tools: "Dosya ve araçlar",
  planning: "Planlama",
  coding: "Kodlama",
  review: "İnceleme",
  headless: "Headless",
  structured_output: "Yapılandırılmış çıktı",
  mcp: "MCP",
  skills: "Skill",
  web_search: "Web arama",
};

// Shown so the roadmap is visible; these adapters are not wired yet.
const PLANNED = [
  { name: "OpenAI Codex", note: "ChatGPT aboneliği gerekli · abonelik alınınca eklenecek", phase: "Sonra" },
  { name: "Grok Build", note: "Koşullu ücretsiz erişim · doğrulanacak", phase: "Faz 2" },
  { name: "Kimi Code", note: "Üyelik gerekli · opsiyonel", phase: "Sonra" },
  { name: "DeepSeek", note: "Ücretli API · varsayılan kapalı", phase: "Sonra" },
];

export function ModelsView({
  models,
  onRefresh,
  onError,
}: {
  models: ModelInfo[];
  onRefresh: () => Promise<void>;
  onError: (msg: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <Page
      title="Model Yöneticisi"
      subtitle="Ücretli API kullanımı kod seviyesinde kapalı. Abonelik dışı giriş algılanırsa model engellenir."
      action={
        <button
          onClick={async () => {
            setBusy(true);
            await onRefresh().finally(() => setBusy(false));
          }}
          className="flex items-center gap-1.5 rounded-lg border border-line-strong px-3 py-1.5 text-[13px] hover:border-white/40"
        >
          <RefreshCw size={13} className={busy ? "animate-spin" : ""} /> Kontrol et
        </button>
      }
    >
      <div className="space-y-3">
        {models.map((m) => (
          <div key={m.id} className="rounded-xl border border-line bg-panel p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2.5">
                  <ModelDot state={m.state} />
                  <span className="text-[15px] font-medium text-fg">{m.name}</span>
                  <span className="font-mono text-[11px] text-faint">{m.provider}</span>
                </div>
                <p className="mt-1 text-[13px] text-dim">{m.notes}</p>
              </div>
              <span className="rounded-full border border-line-strong px-2.5 py-0.5 font-mono text-[10.5px] text-dim">
                {BILLING_LABEL[m.billing]}
              </span>
            </div>

            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div>
                <div className="label mb-1">Durum</div>
                <div className={`text-[13.5px] ${m.state === "paid_access_required" ? "text-danger" : "text-fg"}`}>
                  {MODEL_STATE_LABEL[m.state] ?? m.state}
                </div>
                <div className="mt-0.5 text-[12.5px] text-dim">{m.detail}</div>
                <div className="mt-0.5 font-mono text-[11px] text-faint">{m.auth_method}</div>
              </div>
              <div>
                <div className="label mb-1">
                  Kullanım · {USAGE_SOURCE_LABEL[m.usage.source]}
                </div>
                {m.usage.windows.length === 0 ? (
                  <div className="text-[12.5px] text-dim">{m.usage.detail}</div>
                ) : (
                  <div className="space-y-2">
                    {m.usage.windows.map((w) => (
                      <UsageBar key={w.name} name={WINDOW_LABEL[w.name] ?? w.name} value={w.utilization} resetsAt={w.resets_at} />
                    ))}
                  </div>
                )}
              </div>
            </div>

            {m.data.models && m.data.models.length > 0 && (
              <LocalModels
                models={m.data.models}
                selected={m.data.selected}
                onSelect={async (name) => {
                  try {
                    await api.setPreference("ollama_model", name);
                    await onRefresh();
                  } catch (e) {
                    onError((e as Error).message);
                  }
                }}
              />
            )}

            <div className="mt-4 flex flex-wrap gap-1.5">
              {Object.entries(m.capabilities)
                .filter(([, v]) => v)
                .map(([k]) => (
                  <span key={k} className="rounded border border-line px-1.5 font-mono text-[10px] leading-[18px] text-dim">
                    {CAP_LABEL[k] ?? k}
                  </span>
                ))}
            </div>
          </div>
        ))}
      </div>

      <div className="label mt-10 mb-2">Planlanan adaptörler</div>
      <div className="divide-y divide-line overflow-hidden rounded-xl border border-line">
        {PLANNED.map((m) => (
          <div key={m.name} className="flex items-center gap-3 bg-panel/50 px-4 py-2.5 opacity-70">
            <span className="size-1.5 rounded-full ring-1 ring-faint" />
            <span className="text-[13.5px] text-fg">{m.name}</span>
            <span className="flex-1 truncate text-[12.5px] text-dim">{m.note}</span>
            <span className="font-mono text-[10px] text-faint">{m.phase}</span>
          </div>
        ))}
      </div>
    </Page>
  );
}

/** Utilization as a row of 20 dots. */
function UsageBar({ name, value, resetsAt }: { name: string; value: number | null; resetsAt: number | null }) {
  const lit = Math.round((value ?? 0) * 20);
  return (
    <div>
      <div className="flex justify-between text-[12px] text-dim">
        <span>{name}</span>
        <span className="font-mono">%{Math.round((value ?? 0) * 100)}</span>
      </div>
      <div className="mt-1 flex gap-[3px]" aria-hidden>
        {Array.from({ length: 20 }, (_, i) => (
          <span key={i} className={`size-[5px] rounded-full ${i < lit ? "bg-white" : "bg-white/10"}`} />
        ))}
      </div>
      {resetsAt && (
        <div className="mt-0.5 font-mono text-[10.5px] text-faint">
          sıfırlanma: {new Date(resetsAt * 1000).toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" })}
        </div>
      )}
    </div>
  );
}

function LocalModels({
  models,
  selected,
  onSelect,
}: {
  models: NonNullable<ModelInfo["data"]["models"]>;
  selected?: string;
  onSelect: (name: string) => void;
}) {
  return (
    <div className="mt-4">
      <div className="label mb-1.5">Kurulu modeller · varsayılanı seç</div>
      <div className="divide-y divide-line overflow-hidden rounded-lg border border-line">
        {models.map((lm) => (
          <button
            key={lm.name}
            onClick={() => onSelect(lm.name)}
            className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-white/[0.03]"
            aria-pressed={lm.name === selected}
          >
            <span
              className={`size-2 shrink-0 rounded-full ${lm.name === selected ? "bg-white" : "ring-1 ring-faint"}`}
            />
            <span className="flex-1 truncate font-mono text-[12px] text-fg">{lm.name}</span>
            <span className="font-mono text-[10.5px] text-faint">
              {[lm.params, lm.quant, `${lm.size_gb} GB`].filter(Boolean).join(" · ")}
            </span>
          </button>
        ))}
      </div>
      <p className="mt-1.5 text-[11.5px] text-faint">
        16 GB RAM için 7–8B, Q4 modeller önerilir. Model yalnızca kullanılırken RAM'e yüklenir.
      </p>
    </div>
  );
}
