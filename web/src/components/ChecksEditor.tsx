import { Plus, ShieldAlert, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { ChecksConfig, ChecksInfo, Project } from "../lib/types";

const input =
  "min-w-0 rounded-md border border-line-strong bg-ink px-2.5 py-1.5 font-mono text-[12px] text-fg placeholder:text-faint focus:border-white/40 focus:outline-none";

/** Which commands Orbit runs (in the sandbox) before you review a task's changes. */
export function ChecksEditor({
  project,
  onClose,
  onError,
}: {
  project: Project;
  onClose: () => void;
  onError: (msg: string) => void;
}) {
  const [info, setInfo] = useState<ChecksInfo | null>(null);
  const [draft, setDraft] = useState<ChecksConfig>({ setup: null, commands: [] });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .checks(project.id)
      .then((i) => (setInfo(i), setDraft(structuredClone(i.effective))))
      .catch((e) => onError(e.message));
  }, [project.id, onError]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const save = async (config: ChecksConfig | null) => {
    setBusy(true);
    try {
      const commands = config?.commands.filter((c) => c.name.trim() && c.command.trim()) ?? [];
      const i = await api.saveChecks(project.id, config && { ...config, commands });
      setInfo(i);
      setDraft(structuredClone(i.effective));
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const setCmd = (idx: number, key: "name" | "command", value: string) =>
    setDraft((d) => ({
      ...d,
      commands: d.commands.map((c, i) => (i === idx ? { ...c, [key]: value } : c)),
    }));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4" onClick={onClose}>
      <div
        className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-line-strong bg-panel"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={`${project.name} kalite kontrolleri`}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div>
            <div className="text-[15px] font-medium text-fg">{project.name} · Kalite kontrolleri</div>
            <p className="mt-1 text-[12.5px] leading-relaxed text-dim">
              Ajanlar işini bitirince Orbit bu komutları sandbox içinde kendisi çalıştırır; sonuç
              diff'in yanında gösterilir. Komutlar yalnızca görevin kopyasına yazabilir ve
              internete yalnızca paket depoları üzerinden çıkabilir.
            </p>
          </div>
          <button onClick={onClose} className="text-dim hover:text-fg" aria-label="Kapat">
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {info && !info.sandbox && (
            <div className="flex gap-2 rounded-md border border-danger/30 bg-danger/[0.06] px-3 py-2 text-[12.5px] text-danger">
              <ShieldAlert size={14} className="mt-0.5 shrink-0" />
              Sandbox (srt) kurulu değil; kontroller güvenlik için çalıştırılmayacak. Terminalde
              make setup çalıştırın.
            </div>
          )}
          <div className="font-mono text-[10.5px] text-faint">
            {info?.configured ? "Özel ayar kullanılıyor" : "Projeden otomatik algılandı"}
          </div>
          <div>
            <div className="label mb-1.5">Kurulum (bağımlılıklar, isteğe bağlı)</div>
            <input
              value={draft.setup ?? ""}
              onChange={(e) => setDraft((d) => ({ ...d, setup: e.target.value || null }))}
              placeholder="ör. npm ci"
              className={`${input} w-full`}
            />
          </div>
          <div>
            <div className="label mb-1.5">Kontroller</div>
            <div className="space-y-2">
              {draft.commands.map((c, i) => (
                <div key={i} className="flex gap-2">
                  <input
                    value={c.name}
                    onChange={(e) => setCmd(i, "name", e.target.value)}
                    placeholder="ad"
                    className={`${input} w-32 shrink-0`}
                  />
                  <input
                    value={c.command}
                    onChange={(e) => setCmd(i, "command", e.target.value)}
                    placeholder="komut, ör. npm test"
                    className={`${input} flex-1`}
                  />
                  <button
                    onClick={() => setDraft((d) => ({ ...d, commands: d.commands.filter((_, j) => j !== i) }))}
                    className="px-1 text-faint hover:text-fg"
                    aria-label="Kaldır"
                  >
                    <X size={14} />
                  </button>
                </div>
              ))}
              {draft.commands.length === 0 && (
                <p className="text-[12.5px] text-dim">Kontrol yok; görevler kontrolsüz incelemeye gelir.</p>
              )}
              <button
                onClick={() => setDraft((d) => ({ ...d, commands: [...d.commands, { name: "", command: "" }] }))}
                className="flex items-center gap-1.5 font-mono text-[11px] text-dim hover:text-fg"
              >
                <Plus size={12} /> Kontrol ekle
              </button>
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-line px-5 py-3">
          <button
            onClick={() => void save(null)}
            disabled={busy || !info?.configured}
            className="font-mono text-[11px] text-dim hover:text-fg disabled:opacity-30"
          >
            Otomatik algılamaya dön
          </button>
          <button
            onClick={() => void save(draft)}
            disabled={busy || !info}
            className="rounded-lg bg-white px-3.5 py-1.5 text-[13px] font-medium text-black disabled:opacity-30"
          >
            Kaydet
          </button>
        </div>
      </div>
    </div>
  );
}
