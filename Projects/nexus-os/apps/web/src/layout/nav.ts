import { Bot, Brain, CalendarClock, FolderKanban, LayoutDashboard, Lightbulb, Settings, ShieldCheck, Workflow, type LucideIcon } from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
  /** Show a live count next to the label. */
  badge?: "approvals" | "memory" | "ideas";
}

/** Sections appear here only once the feature behind them exists. */
export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Command Center", icon: LayoutDashboard, end: true },
  { to: "/timeline", label: "Timeline", icon: CalendarClock },
  { to: "/projects", label: "Projects", icon: FolderKanban },
  { to: "/agents", label: "Agents", icon: Bot },
  { to: "/workflows", label: "Workflows", icon: Workflow },
  { to: "/approvals", label: "Approvals", icon: ShieldCheck, badge: "approvals" },
  { to: "/memory", label: "Memory", icon: Brain, badge: "memory" },
  { to: "/ideas", label: "Ideas & notes", icon: Lightbulb, badge: "ideas" },
  { to: "/settings", label: "Settings", icon: Settings },
];
