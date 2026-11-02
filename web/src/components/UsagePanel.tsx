import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { UsageSummary } from "../lib/types";
import { formatTokens } from "./Orchestra";

const HEIGHT = 8; // dots per day column
const RANGES = [7, 30] as const;

const spent = (c: { input: number; output: number }) => c.input + c.output;

function dayLabel(date: string, days: number): string {
  const d = new Date(`${date}T12:00:00`);
  return days <= 7
    ? d.toLocaleDateString("tr-TR", { weekday: "short" })
    : String(d.getDate());
}

/** Tokens per day, per model, and the turns that used the most; drawn in dots. */
export function UsagePanel({
  onOpenChat,
  onError,
}: {
  onOpenChat: (chatId: number) => void;
  onError: (msg: string) => void;
}) {
  const [days, setDays] = useState<(typeof RANGES)[number]>(7);
  const [data, setData] = useState<UsageSummary | null>(null);

  useEffect(() => {
    api
      .usage(days)
      .then(setData)
      .catch((e) => onError((e as Error).message));
  }, [days, onError]);

  const peak = Math.max(1, ...(data?.by_day ?? []).map(spent));
  const total = Math.max(1, data ? spent(data.totals) : 1);

  return (
    <section aria-label="Token kullanımı">
      <div className="mb-1 flex items-center justify-between">
        <div className="label">Token kullanımı</div>
        <div className="flex gap-1">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setDays(r)}
              aria-pressed={days === r}
              className={`rounded-md border px-2 py-0.5 font-mono text-[10.5px] ${
                days === r ? "border-white/50 text-fg" : "border-line text-faint hover:text-dim"
              }`}
            >
              {r} gün
            </button>
          ))}
        </div>
      </div>
      <p className="mb-2 text-[12.5px] leading-relaxed text-dim">
        Her turda hangi modelin ne kadar token harcadığı, sağlayıcıların kendi bildirdiği sayılarla.
        Önbellekten okunan token ayrı gösterilir. Sayı bildirmeyen sağlayıcının turları burada görünmez.
      </p>

      <div className="rounded-xl border border-line bg-panel p-4">
        {data === null ? (
          <div className="font-mono text-[11px] text-faint">yükleniyor…</div>
        ) : data.totals.turns === 0 ? (
          <div className="text-[13px] text-dim">Bu aralıkta token sayısı kayıtlı bir tur yok.</div>
        ) : (
          <>
            <div className="flex flex-wrap gap-x-5 gap-y-1 font-mono text-[11.5px] text-dim">
              <span>
                <span className="text-fg">{formatTokens(data.totals.input)}</span> girdi
              </span>
              <span>
                <span className="text-fg">{formatTokens(data.totals.output)}</span> çıktı
              </span>
              <span>
                <span className="text-fg">{formatTokens(data.totals.cached)}</span> önbellek
              </span>
              <span>
                <span className="text-fg">{data.totals.turns}</span> tur
              </span>
            </div>

            <div className="mt-4 flex items-end gap-1" role="img" aria-label="Günlük token">
              {data.by_day.map((d) => {
                const lit = spent(d) ? Math.max(1, Math.round((spent(d) / peak) * HEIGHT)) : 0;
                return (
                  <div
                    key={d.date}
                    className="flex min-w-0 flex-1 flex-col items-center gap-[3px]"
                    title={`${d.date}: ${formatTokens(spent(d))} token, ${d.turns} tur`}
                  >
                    {Array.from({ length: HEIGHT }, (_, i) => (
                      <span
                        key={i}
                        className={`size-[5px] rounded-full ${HEIGHT - i <= lit ? "bg-white" : "bg-white/10"}`}
                      />
                    ))}
                    <span className="mt-1 font-mono text-[9.5px] text-faint">
                      {dayLabel(d.date, data.days)}
                    </span>
                  </div>
                );
              })}
            </div>

            <div className="mt-5 divide-y divide-line">
              {data.by_model.map((m) => {
                const lit = Math.max(1, Math.round((spent(m) / total) * 20));
                return (
                  <div key={m.model} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
                    <span className="w-14 shrink-0 rounded border border-line-strong text-center font-mono text-[10px] leading-[18px] text-dim">
                      {m.vendor}
                    </span>
                    <span className="w-28 truncate text-[13px] text-fg">{m.model}</span>
                    <span className="flex gap-[3px]" aria-hidden>
                      {Array.from({ length: 20 }, (_, i) => (
                        <span
                          key={i}
                          className={`size-[4px] rounded-full ${i < lit ? "bg-white" : "bg-white/10"}`}
                        />
                      ))}
                    </span>
                    <span className="ml-auto font-mono text-[10.5px] text-faint">
                      {formatTokens(m.input)} girdi · {formatTokens(m.output)} çıktı ·{" "}
                      {formatTokens(m.cached)} önbellek · {m.turns} tur
                    </span>
                  </div>
                );
              })}
            </div>

            {data.top_turns.length > 0 && (
              <>
                <div className="label mt-5 mb-1.5">En çok harcayan turlar</div>
                <div className="divide-y divide-line overflow-hidden rounded-lg border border-line">
                  {data.top_turns.map((t) => (
                    <button
                      key={t.message_id}
                      onClick={() => onOpenChat(t.chat_id)}
                      className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-white/[0.03]"
                    >
                      <span className="flex-1 truncate text-[13px] text-fg">{t.chat_title}</span>
                      <span className="hidden truncate font-mono text-[10.5px] text-faint sm:inline">
                        {t.models.join(", ")}
                      </span>
                      <span className="font-mono text-[11px] text-dim">
                        {formatTokens(spent(t))}
                      </span>
                      <span className="font-mono text-[10px] text-faint">
                        {new Date(`${t.date}T12:00:00`).toLocaleDateString("tr-TR", {
                          day: "numeric",
                          month: "short",
                        })}
                      </span>
                    </button>
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </section>
  );
}
