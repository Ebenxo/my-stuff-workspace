import { FolderKanban, LayoutDashboard, Settings, type LucideIcon } from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

/** Sections appear here only once the feature behind them exists. */
export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Command Center", icon: LayoutDashboard, end: true },
  { to: "/projects", label: "Projects", icon: FolderKanban },
  { to: "/settings", label: "Settings", icon: Settings },
];
