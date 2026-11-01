import { Plus, Trash2, X } from "lucide-react";
import { NAV_GROUPS, type ViewId } from "../lib/nav";
import type { Chat, ModelInfo } from "../lib/types";
import { DotMark } from "./DotMatrix";
import { ModelDot } from "./StatusDot";

interface Props {
  view: ViewId;
  chatId: number | null;
  chats: Chat[];
  models: ModelInfo[];
  pendingApprovals: number;
  connected: boolean;
  open: boolean;
  onClose: () => void;
  onNavigate: (v: ViewId) => void;
  onOpenChat: (id: number) => void;
  onNewChat: () => void;
  onDeleteChat: (id: number) => void;
}

export function Sidebar(p: Props) {
  return (
    <>
      {p.open && (
        <div className="fixed inset-0 z-30 bg-black/70 md:hidden" onClick={p.onClose} aria-hidden />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-line bg-panel transition-transform md:static md:translate-x-0 ${
          p.open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-14 items-center justify-between px-4">
          <button
            onClick={() => p.onNavigate("chat")}
            className="flex items-center gap-2.5"
            aria-label="Ana ekran"
          >
            <DotMark />
            <span className="font-mono text-[11px] tracking-[0.22em] text-fg">KOMUTA MERKEZİ</span>
          </button>
          <button onClick={p.onClose} className="text-dim md:hidden" aria-label="Menüyü kapat">
            <X size={16} />
          </button>
        </div>

        <div className="px-3">
          <button
            onClick={p.onNewChat}
            className="flex w-full items-center gap-2 rounded-lg border border-line-strong px-3 py-2 text-[13px] text-fg transition-colors hover:bg-white hover:text-black"
          >
            <Plus size={14} />
            Yeni sohbet
          </button>
        </div>

        <nav className="mt-4 flex-1 overflow-y-auto px-3 pb-4">
          {NAV_GROUPS.map((g) => (
            <div key={g.title} className="mb-4">
              <div className="label mb-1.5 px-2">{g.title}</div>
              {g.items.map((it) => {
                const active = p.view === it.id;
                const Icon = it.icon;
                return (
                  <button
                    key={it.id}
                    onClick={() => p.onNavigate(it.id)}
                    className={`group flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-[13px] transition-colors ${
                      active ? "bg-white/[0.07] text-fg" : "text-dim hover:text-fg"
                    } ${it.phase ? "opacity-60" : ""}`}
                  >
                    <Icon size={14} strokeWidth={1.6} />
                    <span className="flex-1 text-left">{it.label}</span>
                    {it.id === "approvals" && p.pendingApprovals > 0 && (
                      <span className="rounded-full bg-white px-1.5 font-mono text-[10px] leading-4 text-black">
                        {p.pendingApprovals}
                      </span>
                    )}
                    {it.phase && <span className="font-mono text-[9px] text-faint">{it.phase}</span>}
                  </button>
                );
              })}
            </div>
          ))}

          {p.chats.length > 0 && (
            <div>
              <div className="label mb-1.5 px-2">Son sohbetler</div>
              {p.chats.map((c) => (
                <div
                  key={c.id}
                  className={`group flex items-center rounded-md ${
                    p.view === "chat" && p.chatId === c.id ? "bg-white/[0.07]" : ""
                  }`}
                >
                  <button
                    onClick={() => p.onOpenChat(c.id)}
                    className={`flex-1 truncate px-2 py-1.5 text-left text-[13px] ${
                      p.chatId === c.id ? "text-fg" : "text-dim hover:text-fg"
                    }`}
                    title={c.title}
                  >
                    {c.title}
                  </button>
                  <button
                    onClick={() => p.onDeleteChat(c.id)}
                    className="px-2 text-faint opacity-0 transition-opacity hover:text-fg group-hover:opacity-100 focus:opacity-100"
                    aria-label="Sohbeti sil"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </nav>

        <div className="border-t border-line px-4 py-3">
          <div className="flex items-center justify-between">
            <span className="label">Modeller</span>
            <span className="flex items-center gap-1.5 font-mono text-[10px] text-faint">
              <span
                className={`size-1.5 rounded-full ${connected(p.connected)}`}
                aria-hidden
              />
              {p.connected ? "canlı" : "bağlanıyor"}
            </span>
          </div>
          <div className="mt-2 space-y-1">
            {p.models.map((m) => (
              <div key={m.id} className="flex items-center gap-2 text-[12px] text-dim">
                <ModelDot state={m.state} />
                {m.name}
              </div>
            ))}
          </div>
        </div>
      </aside>
    </>
  );
}

const connected = (on: boolean) => (on ? "bg-white" : "bg-faint animate-blink");
