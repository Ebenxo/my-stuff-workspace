import { Bot, Brain, FolderKanban, LayoutDashboard, Settings, ShieldCheck, type LucideIcon } from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
  /** Show a live count next to the label. */
  badge?: "approvals" | "memory";
}

/** Sections appear here only once the feature behind them exists. */
export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Command Center", icon: LayoutDashboard, end: true },
  { to: "/projects", label: "Projects", icon: FolderKanban },
  { to: "/agents", label: "Agents", icon: Bot },
  { to: "/approvals", label: "Approvals", icon: ShieldCheck, badge: "approvals" },
  { to: "/memory", label: "Memory", icon: Brain, badge: "memory" },
  { to: "/settings", label: "Settings", icon: Settings },
];
