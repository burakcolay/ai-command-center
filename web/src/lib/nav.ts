import {
  BookMarked,
  Bot,
  Cpu,
  FolderKanban,
  Gauge,
  GitBranch,
  Globe,
  Library,
  type LucideIcon,
  Plug,
  Settings,
  ShieldCheck,
  Workflow,
} from "lucide-react";

export type ViewId =
  | "chat"
  | "projects"
  | "approvals"
  | "agents"
  | "models"
  | "github"
  | "browser"
  | "mcp"
  | "skills"
  | "knowledge"
  | "workflow"
  | "resources"
  | "settings";

export interface NavItem {
  id: ViewId;
  label: string;
  icon: LucideIcon;
  /** Set when the screen isn't built yet: which roadmap phase brings it. */
  phase?: string;
  blurb?: string;
}

export const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: "Çalışma",
    items: [
      { id: "projects", label: "Projeler", icon: FolderKanban },
      { id: "approvals", label: "Onay Merkezi", icon: ShieldCheck },
      { id: "agents", label: "Ajanlar", icon: Bot },
      { id: "models", label: "Model Yöneticisi", icon: Cpu },
    ],
  },
  {
    title: "Araçlar",
    items: [
      {
        id: "github",
        label: "GitHub",
        icon: GitBranch,
        phase: "Faz 4",
        blurb: "Repo, branch, issue ve PR işlemleri; riskli işlemler onaylı.",
      },
      {
        id: "browser",
        label: "Tarayıcı Oturumları",
        icon: Globe,
        phase: "Faz 4",
        blurb: "Ayrı Playwright profilleriyle kontrollü web işlemleri.",
      },
      {
        id: "mcp",
        label: "MCP Merkezi",
        icon: Plug,
        phase: "Faz 4",
        blurb: "MCP sunucu kaydı, sağlık kontrolü ve ajan bazlı yetkilendirme.",
      },
      {
        id: "skills",
        label: "Yetenek Kütüphanesi",
        icon: Library,
        phase: "Faz 5",
        blurb: "SKILL.md tabanlı yetenekler; karantina, inceleme ve onaylı kurulum.",
      },
      {
        id: "knowledge",
        label: "Bilgi Bankası",
        icon: BookMarked,
        phase: "Faz 4",
        blurb: "Obsidian kasası üzerinden proje kararları ve araştırma notları.",
      },
      {
        id: "workflow",
        label: "İş Akışları",
        icon: Workflow,
        phase: "Faz 8",
        blurb: "Tekrar kullanılabilir çok ajanlı akışlar.",
      },
    ],
  },
  {
    title: "Sistem",
    items: [
      {
        id: "resources",
        label: "Kaynak Yöneticisi",
        icon: Gauge,
        phase: "Faz 7",
        blurb: "RAM, CPU, disk, Ollama modelleri ve görev kaynak planlaması.",
      },
      { id: "settings", label: "Ayarlar", icon: Settings },
    ],
  },
];

export const NAV_ITEMS = NAV_GROUPS.flatMap((g) => g.items);
