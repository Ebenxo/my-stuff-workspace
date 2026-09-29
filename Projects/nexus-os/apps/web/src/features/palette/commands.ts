/** The command palette's commands and how a query ranks them. Pure data and functions. */

export type PaletteAction = "demo" | "toggle-activity" | "toggle-bottom" | "terminal" | "shortcuts";

export interface PaletteCommand {
  id: string;
  label: string;
  group: string;
  hint?: string;
  keywords?: string[];
  to?: string; // navigate here
  action?: PaletteAction; // or do this
}

export const COMMANDS: PaletteCommand[] = [
  { id: "go-home", group: "Go to", label: "Command Center", to: "/", keywords: ["home", "dashboard", "start"] },
  { id: "go-projects", group: "Go to", label: "Projects", to: "/projects" },
  { id: "go-agents", group: "Go to", label: "Agents", to: "/agents", keywords: ["team", "runs"] },
  { id: "go-workflows", group: "Go to", label: "Workflows", to: "/workflows", keywords: ["automation", "schedule"] },
  { id: "go-approvals", group: "Go to", label: "Approvals", to: "/approvals", keywords: ["review", "permissions"] },
  { id: "go-memory", group: "Go to", label: "Memory", to: "/memory", keywords: ["remember", "facts"] },
  { id: "go-search", group: "Go to", label: "Search", to: "/search", keywords: ["find"] },
  { id: "go-settings", group: "Settings", label: "General settings", to: "/settings", keywords: ["name", "workspace", "permission level"] },
  { id: "go-providers", group: "Settings", label: "AI providers", to: "/settings/providers", keywords: ["models", "api key", "anthropic", "openai", "ollama", "lm studio", "gemini"] },
  { id: "go-tools", group: "Settings", label: "Tools & approvals", to: "/settings/tools", keywords: ["permissions", "session"] },
  { id: "go-integrations", group: "Settings", label: "Integrations (MCP servers)", to: "/settings/integrations", keywords: ["mcp", "servers", "connect"] },
  { id: "go-usage", group: "Settings", label: "Usage & budgets", to: "/settings/usage", keywords: ["cost", "tokens", "spend"] },
  { id: "go-health", group: "Settings", label: "System health", to: "/settings/health", keywords: ["status", "audit", "verify"] },
  { id: "new-objective", group: "Create", label: "New objective", to: "/?focus=objective", keywords: ["goal", "task", "plan"] },
  { id: "new-project", group: "Create", label: "New project", to: "/projects?new=1" },
  { id: "new-workflow", group: "Create", label: "New workflow", to: "/workflows?new=1", keywords: ["automation"] },
  { id: "new-mcp", group: "Create", label: "Add an MCP server", to: "/settings/integrations?add=1", keywords: ["integration", "connect", "tools"] },
  { id: "new-provider", group: "Create", label: "Connect an AI provider", to: "/settings/providers?add=1", keywords: ["model", "api key"] },
  { id: "demo", group: "Create", label: "Try the demo", action: "demo", hint: "Runs a scripted example objective", keywords: ["example", "sample"] },
  { id: "toggle-activity", group: "View", label: "Show or hide the activity panel", action: "toggle-activity", keywords: ["events", "side panel"] },
  { id: "toggle-bottom", group: "View", label: "Show or hide the bottom panel", action: "toggle-bottom", keywords: ["events", "errors", "logs"] },
  { id: "terminal", group: "View", label: "Open the NEXUS command line", action: "terminal", keywords: ["terminal", "console"] },
  { id: "shortcuts", group: "View", label: "Keyboard shortcuts", action: "shortcuts", keywords: ["keys", "help"] },
];

/** How well ``text`` matches ``query`` (0 = not at all). Prefix beats word start beats substring beats scattered letters. */
export function score(query: string, text: string): number {
  const q = query.trim().toLowerCase();
  const t = text.toLowerCase();
  if (!q) return 1;
  if (t === q) return 100;
  if (t.startsWith(q)) return 80;
  if (t.split(/[\s/·&()-]+/).some((w) => w.startsWith(q))) return 60;
  if (t.includes(q)) return 40;
  // letters in order ("nwf" → "New workflow"), closer together is better
  let at = -1;
  let first = -1;
  for (const ch of q) {
    if (ch === " ") continue;
    at = t.indexOf(ch, at + 1);
    if (at < 0) return 0;
    if (first < 0) first = at;
  }
  const spread = at - first + 1;
  return Math.max(1, 20 - Math.min(19, spread - q.replace(/\s/g, "").length));
}

export function commandScore(query: string, c: Pick<PaletteCommand, "label" | "keywords" | "group">): number {
  const own = score(query, c.label);
  const extra = Math.max(0, ...(c.keywords ?? []).map((k) => score(query, k)), score(query, `${c.group} ${c.label}`));
  return Math.max(own, Math.floor(extra * 0.9));
}

/** Commands matching the query, best first (ties keep their listed order). An empty query lists everything. */
export function rank<T extends Pick<PaletteCommand, "label" | "keywords" | "group">>(query: string, commands: T[]): T[] {
  if (!query.trim()) return commands;
  return commands
    .map((c, i) => ({ c, i, s: commandScore(query, c) }))
    .filter((x) => x.s > 0)
    .sort((a, b) => b.s - a.s || a.i - b.i)
    .map((x) => x.c);
}

export interface PaletteItem {
  id: string;
  label: string;
  group: string;
  hint?: string | undefined;
  to?: string | undefined;
  action?: PaletteAction | undefined;
}

interface ProjectLike {
  id: string;
  name: string;
  status?: string | undefined;
}

interface HitLike {
  kind: string;
  id: string;
  title: string;
  href: string;
}

const GROUP_ORDER = ["Create", "Go to", "Projects", "Settings", "View"];

/** Everything the palette shows for a query: commands, projects, search results, and "search everything". */
export function paletteItems(query: string, projects: ProjectLike[], hits: HitLike[] = []): PaletteItem[] {
  const q = query.trim();
  const projectItems: PaletteItem[] = projects
    .filter((p) => p.status !== "archived")
    .map((p) => ({ id: `project-${p.id}`, group: "Projects", label: p.name, to: `/projects/${p.id}`, hint: "Project" }));
  if (!q) {
    const all = [...COMMANDS, ...projectItems.slice(0, 5)];
    return GROUP_ORDER.flatMap((g) => all.filter((c) => c.group === g));
  }
  const ranked = rank(q, [...COMMANDS, ...projectItems]).slice(0, 12);
  const seen = new Set(ranked.map((r) => r.to));
  const found: PaletteItem[] = hits
    .filter((h) => !seen.has(h.href))
    .slice(0, 6)
    .map((h) => ({ id: `hit-${h.kind}-${h.id}`, group: "Found", label: h.title, to: h.href, hint: h.kind }));
  return [...ranked, ...found, { id: "search-all", group: "Search", label: `Search everything for “${q}”`, to: `/search?q=${encodeURIComponent(q)}` }];
}
