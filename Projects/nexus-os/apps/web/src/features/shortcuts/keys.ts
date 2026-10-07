/** Keyboard shortcuts: what each key does, and the list the help dialog shows. Pure, so it is testable. */

export type ShortcutAction = "palette" | "shortcuts" | "search" | "toggle-bottom" | "toggle-activity" | `go:${string}`;

/** "g" then a letter goes somewhere. */
export const GO: Record<string, { to: string; label: string }> = {
  c: { to: "/", label: "Command Center" },
  t: { to: "/timeline", label: "Timeline" },
  p: { to: "/projects", label: "Projects" },
  a: { to: "/agents", label: "Agents" },
  w: { to: "/workflows", label: "Workflows" },
  r: { to: "/approvals", label: "Approvals (review)" },
  m: { to: "/memory", label: "Memory" },
  i: { to: "/ideas", label: "Ideas & notes" },
  s: { to: "/settings", label: "Settings" },
};

export interface ShortcutHelp {
  keys: string[];
  label: string;
}

export function shortcutList(mac: boolean): { group: string; items: ShortcutHelp[] }[] {
  const mod = mac ? "⌘" : "Ctrl";
  return [
    {
      group: "Anywhere",
      items: [
        { keys: [mod, "K"], label: "Open the command palette" },
        { keys: ["/"], label: "Search everything" },
        { keys: ["?"], label: "Show these shortcuts" },
        { keys: [mod, "J"], label: "Show or hide the bottom panel (events, terminal)" },
        { keys: [mod, "."], label: "Show or hide the activity panel" },
        { keys: ["Esc"], label: "Close a dialog or panel" },
      ],
    },
    { group: "Go to", items: Object.entries(GO).map(([k, g]) => ({ keys: ["G", k.toUpperCase()], label: g.label })) },
    {
      group: "While writing",
      items: [
        { keys: [mod, "Enter"], label: "Start the objective (Command Center)" },
        { keys: ["↑", "↓", "Enter"], label: "Move through and choose palette results" },
      ],
    },
  ];
}

export interface KeyLike {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
  shiftKey: boolean;
}

/**
 * What a key press means. ``typing`` is true when focus is in a text field: then only the modifier
 * shortcuts apply, so writing "g" or "/" never navigates. ``pendingG`` carries the first key of a
 * "g then letter" pair.
 */
export function resolveKey(e: KeyLike, state: { pendingG: boolean; typing: boolean }): { action?: ShortcutAction; pendingG: boolean } {
  const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  const mod = e.ctrlKey || e.metaKey;
  if (mod && !e.altKey) {
    if (key === "k") return { action: "palette", pendingG: false };
    if (key === "j") return { action: "toggle-bottom", pendingG: false };
    if (key === ".") return { action: "toggle-activity", pendingG: false };
    return { pendingG: false };
  }
  if (state.typing || e.altKey || mod) return { pendingG: false };
  if (state.pendingG) {
    const go = GO[key];
    return go ? { action: `go:${go.to}`, pendingG: false } : { pendingG: false };
  }
  if (key === "g" && !e.shiftKey) return { pendingG: true };
  if (key === "/") return { action: "search", pendingG: false };
  if (e.key === "?") return { action: "shortcuts", pendingG: false };
  return { pendingG: false };
}

export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT") {
    const type = (target as HTMLInputElement).type;
    return !["checkbox", "radio", "button", "submit", "reset", "range", "color", "file"].includes(type);
  }
  return tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

export function isMac(): boolean {
  return typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
}
