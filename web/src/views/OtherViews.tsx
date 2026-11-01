import { Lock, ShieldCheck } from "lucide-react";
import { StatusPill } from "../components/StatusDot";
import type { NavItem } from "../lib/nav";
import type { Agent, Approval } from "../lib/types";
import { Empty, Page } from "./Page";

export function AgentsView({ agents }: { agents: Agent[] }) {
  return (
    <Page
      title="Ajanlar"
      subtitle="Her ajan bir rol, izinli araçlar ve tercih edilen modellerden oluşur. Araç kısıtları CLI seviyesinde uygulanır."
    >
      <div className="grid gap-3 md:grid-cols-2">
        {agents.map((a) => (
          <div key={a.id} className="rounded-xl border border-line bg-panel p-4">
            <div className="flex items-center justify-between">
              <span className="text-[14.5px] font-medium text-fg">{a.name}</span>
              <span className="font-mono text-[10px] uppercase tracking-wider text-faint">
                {a.writes_files ? "yazabilir" : "salt okunur"}
              </span>
            </div>
            <p className="mt-1 text-[13px] leading-relaxed text-dim">{a.description}</p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {a.tools.map((t) => (
                <span key={t} className="rounded border border-line px-1.5 font-mono text-[10px] leading-[18px] text-dim">
                  {t}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Page>
  );
}

export function ApprovalsView({
  approvals,
  onOpenTask,
}: {
  approvals: Approval[];
  onOpenTask: (chatId: number) => void;
}) {
  return (
    <Page title="Onay Merkezi" subtitle="Onayınızı bekleyen planlar ve işlemler. Tüm kararlar kayıt altına alınır.">
      {approvals.length === 0 ? (
        <Empty>
          <ShieldCheck size={18} className="mx-auto mb-2 text-faint" />
          Bekleyen onay yok.
        </Empty>
      ) : (
        <div className="divide-y divide-line overflow-hidden rounded-xl border border-line">
          {approvals.map((a) => (
            <button
              key={a.id}
              onClick={() => onOpenTask(a.task.chat_id)}
              className="flex w-full items-center gap-4 bg-panel px-4 py-3 text-left hover:bg-raised"
            >
              <span className="font-mono text-[10.5px] uppercase tracking-wider text-faint">
                {a.kind === "plan" ? "Plan" : a.kind === "merge" ? "Birleştirme" : a.kind}
              </span>
              <span className="min-w-0 flex-1 truncate text-[14px] text-fg">{a.task.title}</span>
              <StatusPill status={a.task.status} />
            </button>
          ))}
        </div>
      )}
    </Page>
  );
}

export function SettingsView({ demoMode }: { demoMode: boolean }) {
  return (
    <Page title="Ayarlar" subtitle="Güvenlik ve maliyet politikası. Bu kurallar arayüzden değiştirilemez.">
      <div className="space-y-px overflow-hidden rounded-xl border border-line">
        {[
          ["Ücretli API kullanımı", "Kapalı — kodda sabit. API anahtarı ortam değişkenleri alt süreçlere aktarılmaz."],
          ["Abonelik doğrulaması", "Claude Code her çalıştırmada abonelik girişini doğrular; API anahtarı algılanırsa durur."],
          ["Ücretli aşım (extra usage)", "Algılanırsa çalıştırma durdurulur. claude.ai ve ChatGPT ayarlarında kapalı tutun."],
          ["Ağ erişimi", "Sunucu yalnızca 127.0.0.1 üzerinde dinler; farklı host başlıkları reddedilir."],
          ["Demo modu", demoMode ? "Açık (ACC_DEMO=1)" : "Kapalı"],
        ].map(([k, v]) => (
          <div key={k} className="flex flex-col gap-1 bg-panel px-4 py-3 md:flex-row md:items-center md:gap-6">
            <div className="flex w-56 shrink-0 items-center gap-2 text-[13.5px] text-fg">
              <Lock size={12} className="text-faint" />
              {k}
            </div>
            <div className="text-[13px] text-dim">{v}</div>
          </div>
        ))}
      </div>
    </Page>
  );
}

export function ComingSoon({ item }: { item: NavItem }) {
  const Icon = item.icon;
  return (
    <Page title={item.label}>
      <Empty>
        <Icon size={20} strokeWidth={1.4} className="mx-auto mb-3 text-dim" />
        <div className="text-fg">{item.blurb}</div>
        <div className="mt-2 font-mono text-[11px] tracking-wider text-faint">{item.phase} ile geliyor</div>
      </Empty>
    </Page>
  );
}
