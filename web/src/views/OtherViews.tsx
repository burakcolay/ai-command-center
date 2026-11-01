import { Lock, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import { StatusPill } from "../components/StatusDot";
import type { NavItem } from "../lib/nav";
import type { Agent, Approval, SystemInfo } from "../lib/types";
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

const QUALITY = [
  { id: "economy", label: "Ekonomik", note: "Daha az düşünür, kota daha uzun dayanır." },
  { id: "balanced", label: "Dengeli", note: "Sohbet ve planlama derin düşünür. Önerilen." },
  { id: "best", label: "En iyi", note: "En derin düşünme; kota en hızlı biter." },
] as const;

const MODELS = [
  { id: "default", label: "Varsayılan", note: "Aboneliğinin seçtiği model" },
  { id: "sonnet", label: "Sonnet", note: "Hızlı, kotayı idareli kullanır" },
  { id: "opus", label: "Opus", note: "Daha güçlü; kotayı daha hızlı kullanır" },
  { id: "fable", label: "Fable", note: "En yeni model; aboneliğinde yoksa hata verir" },
] as const;

export function SettingsView({
  system,
  onToggleNotifications,
  onPreference,
  onError,
}: {
  system: SystemInfo | null;
  onToggleNotifications: (on: boolean) => void;
  onPreference: (key: "quality" | "claude_model", value: string) => void;
  onError: (msg: string) => void;
}) {
  const [tested, setTested] = useState<string | null>(null);
  const test = async () => {
    try {
      const r = await api.testNotification();
      setTested(r.sent ? "Gönderildi — ekranın sağ üstüne bak." : "Bu sistemde desteklenmiyor.");
    } catch (e) {
      onError((e as Error).message);
    }
  };
  return (
    <Page title="Ayarlar">
      <div className="label mb-2">Claude · model ve düşünme</div>
      <div className="mb-8 space-y-4 rounded-xl border border-line bg-panel px-4 py-4">
        <Choice
          title="Kalite"
          options={QUALITY}
          value={system?.quality}
          onChange={(v) => onPreference("quality", v)}
        />
        <Choice
          title="Model"
          options={MODELS}
          value={system?.claude_model}
          onChange={(v) => onPreference("claude_model", v)}
        />
        <p className="text-[12px] leading-relaxed text-faint">
          Araştırma modu her zaman bir kademe daha derin düşünür. Model aboneliğinde yoksa
          çalıştırma açık bir hata verir; ücretli kullanıma geçilmez.
        </p>
      </div>

      <div className="label mb-2">Bildirimler</div>
      <div className="mb-8 overflow-hidden rounded-xl border border-line bg-panel px-4 py-3">
        {system?.notifications_supported ? (
          <div className="flex flex-wrap items-center gap-4">
            <label className="flex flex-1 cursor-pointer items-center gap-3 text-[13.5px] text-fg">
              <input
                type="checkbox"
                checked={system.notifications}
                onChange={(e) => onToggleNotifications(e.target.checked)}
                className="size-4 accent-white"
              />
              Plan hazır, incelemeye hazır, kota doldu veya görev başarısız olduğunda macOS bildirimi gönder
            </label>
            <button
              onClick={() => void test()}
              className="rounded-lg border border-line-strong px-3 py-1 text-[12.5px] hover:border-white/40"
            >
              Test bildirimi
            </button>
            {tested && <span className="w-full font-mono text-[11px] text-dim">{tested}</span>}
          </div>
        ) : (
          <p className="text-[13px] text-dim">Bildirimler yalnızca macOS'ta çalışır.</p>
        )}
      </div>

      <div className="label mb-2">Güvenlik ve maliyet · arayüzden değiştirilemez</div>
      <div className="space-y-px overflow-hidden rounded-xl border border-line">
        {[
          ["Ücretli API", "Kapalı — kodda sabit. API anahtarları alt süreçlere aktarılmaz."],
          ["Abonelik doğrulaması", "Her çalıştırmada; API anahtarı veya ücretli aşım algılanırsa durur."],
          ["Kota dolduğunda", "Görev bekler ve sıfırlanınca kendiliğinden devam eder; ücretliye geçilmez."],
          ["Gizli dosyalar", ".env, anahtar ve sertifika dosyalarını ajanlar okuyamaz."],
          ["Sandbox", "Komut çalıştıran ajanlar ve kalite kontrolleri yalnızca görevin kopyasına yazabilir."],
          ["Kalite kontrolleri", system?.sandbox_for_checks ? "Sandbox hazır" : "Sandbox kurulu değil — make setup"],
          ["Ağ", "Yalnızca 127.0.0.1; başka sitelerden gelen istekler reddedilir."],
          ["Loglar", "Token ve şifre benzeri değerler kaydedilmeden önce maskelenir."],
          ["Proje hafızası", system?.memory_dir ?? "…"],
          ["Demo modu", system?.demo_mode ? "Açık (ACC_DEMO=1)" : "Kapalı"],
        ].map(([k, v]) => (
          <div key={k} className="flex flex-col gap-1 bg-panel px-4 py-3 md:flex-row md:items-center md:gap-6">
            <div className="flex w-48 shrink-0 items-center gap-2 text-[13.5px] text-fg">
              <Lock size={12} className="text-faint" />
              {k}
            </div>
            <div className="min-w-0 break-words text-[13px] text-dim">{v}</div>
          </div>
        ))}
      </div>
    </Page>
  );
}

function Choice<T extends string>({
  title,
  options,
  value,
  onChange,
}: {
  title: string;
  options: readonly { id: T; label: string; note: string }[];
  value?: T;
  onChange: (v: T) => void;
}) {
  return (
    <div>
      <div className="mb-1.5 text-[13px] text-fg">{title}</div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {options.map((o) => (
          <button
            key={o.id}
            onClick={() => onChange(o.id)}
            aria-pressed={value === o.id}
            className={`rounded-lg border px-3 py-2 text-left transition-colors ${
              value === o.id ? "border-white bg-white/[0.06]" : "border-line hover:border-white/30"
            }`}
          >
            <div className="text-[13px] text-fg">{o.label}</div>
            <div className="mt-0.5 text-[11.5px] leading-snug text-dim">{o.note}</div>
          </button>
        ))}
      </div>
    </div>
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
