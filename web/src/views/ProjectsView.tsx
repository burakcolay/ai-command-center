import { BookMarked, Folder, Plus, ShieldCheck, X } from "lucide-react";
import { useState } from "react";
import { ChecksEditor } from "../components/ChecksEditor";
import { MemoryEditor } from "../components/MemoryEditor";
import { api } from "../lib/api";
import type { Project } from "../lib/types";
import { Empty, inputCls, Page } from "./Page";

interface Props {
  projects: Project[];
  onChanged: () => void;
  onOpen: (p: Project) => void;
  onError: (msg: string) => void;
}

export function ProjectsView({ projects, onChanged, onOpen, onError }: Props) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [memoryFor, setMemoryFor] = useState<Project | null>(null);
  const [checksFor, setChecksFor] = useState<Project | null>(null);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createProject(name.trim(), path.trim());
      setName("");
      setPath("");
      setAdding(false);
      onChanged();
    } catch (err) {
      onError((err as Error).message);
    }
  };

  const remove = async (p: Project) => {
    if (!confirm(`"${p.name}" uygulamadan kaldırılsın mı? Diskteki dosyalar silinmez.`)) return;
    try {
      await api.removeProject(p.id);
      onChanged();
    } catch (err) {
      onError((err as Error).message);
    }
  };

  return (
    <Page
      title="Projeler"
      subtitle="Her proje ayrı bir klasör. Ajanlar yalnızca görevin projesine erişir."
      action={
        !adding && (
          <button
            onClick={() => setAdding(true)}
            className="flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-[13px] font-medium text-black"
          >
            <Plus size={14} /> Proje ekle
          </button>
        )
      }
    >
      {adding && (
        <form onSubmit={create} className="mb-6 space-y-3 rounded-xl border border-line bg-panel p-4">
          <div>
            <div className="label mb-1.5">İsim</div>
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="ör. Rahva"
              className={inputCls}
            />
          </div>
          <div>
            <div className="label mb-1.5">Mevcut klasör (isteğe bağlı)</div>
            <input
              value={path}
              onChange={(e) => setPath(e.target.value)}
              placeholder="~/Developer/rahva — boş bırakılırsa workspace/projects altında yeni klasör açılır"
              className={`${inputCls} font-mono text-[12.5px]`}
            />
          </div>
          <div className="flex gap-2">
            <button
              disabled={!name.trim()}
              className="rounded-lg bg-white px-3.5 py-1.5 text-[13px] font-medium text-black disabled:opacity-30"
            >
              Ekle
            </button>
            <button
              type="button"
              onClick={() => setAdding(false)}
              className="rounded-lg border border-line-strong px-3.5 py-1.5 text-[13px]"
            >
              Vazgeç
            </button>
          </div>
        </form>
      )}

      {projects.length === 0 && !adding ? (
        <Empty>Henüz proje yok. Mevcut bir klasörü ekleyin ya da yeni bir proje açın.</Empty>
      ) : (
        <div className="divide-y divide-line overflow-hidden rounded-xl border border-line">
          {projects.map((p) => (
            <div key={p.id} className="group flex items-center gap-3 bg-panel px-4 py-3">
              <Folder size={15} strokeWidth={1.6} className="shrink-0 text-dim" />
              <button onClick={() => onOpen(p)} className="min-w-0 flex-1 text-left">
                <div className="text-[14px] text-fg">{p.name}</div>
                <div className="truncate font-mono text-[11px] text-faint">{p.path}</div>
              </button>
              <button
                onClick={() => setChecksFor(p)}
                className="flex shrink-0 items-center gap-1.5 rounded-md border border-line px-2 py-1 font-mono text-[10.5px] text-dim hover:border-white/30 hover:text-fg"
                title="Kalite kontrolleri: incelemeden önce sandbox'ta çalışan test ve lint komutları"
              >
                <ShieldCheck size={11} /> Kontroller
              </button>
              <button
                onClick={() => setMemoryFor(p)}
                className="flex shrink-0 items-center gap-1.5 rounded-md border border-line px-2 py-1 font-mono text-[10.5px] text-dim hover:border-white/30 hover:text-fg"
                title="Proje hafızası: her ajana verilen kalıcı kararlar ve kurallar"
              >
                <BookMarked size={11} /> Hafıza
              </button>
              <button
                onClick={() => remove(p)}
                className="text-faint opacity-0 hover:text-fg group-hover:opacity-100 focus:opacity-100"
                aria-label="Kaldır"
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
      {checksFor && (
        <ChecksEditor project={checksFor} onClose={() => setChecksFor(null)} onError={onError} />
      )}
      {memoryFor && (
        <MemoryEditor project={memoryFor} onClose={() => setMemoryFor(null)} onError={onError} />
      )}
    </Page>
  );
}
