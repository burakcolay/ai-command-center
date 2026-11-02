import { Cpu, FolderKanban, type LucideIcon, Settings, ShieldCheck } from "lucide-react";

export type ViewId = "chat" | "projects" | "approvals" | "models" | "settings";

export interface NavItem {
  id: ViewId;
  label: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { id: "projects", label: "Projeler", icon: FolderKanban },
  { id: "approvals", label: "Onay Merkezi", icon: ShieldCheck },
  { id: "models", label: "Model Yöneticisi", icon: Cpu },
  { id: "settings", label: "Ayarlar", icon: Settings },
];
