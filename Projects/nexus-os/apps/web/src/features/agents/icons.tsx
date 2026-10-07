import { Bot, ChartColumn, Code, Folder, ListChecks, PenLine, Palette, Scale, Search, ShieldCheck, Workflow, type LucideIcon } from "lucide-react";

const ICONS: Record<string, LucideIcon> = {
  bot: Bot,
  workflow: Workflow,
  "list-checks": ListChecks,
  search: Search,
  code: Code,
  "bar-chart": ChartColumn,
  "pen-line": PenLine,
  palette: Palette,
  folder: Folder,
  scale: Scale,
  "shield-check": ShieldCheck,
};

/** An agent's icon by name. Unknown names fall back to a generic bot. */
export function AgentIcon({ name, className }: { name: string; className?: string }) {
  const Icon = ICONS[name] ?? Bot;
  return <Icon className={className} aria-hidden="true" />;
}
