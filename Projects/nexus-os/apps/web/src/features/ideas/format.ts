/** Pure helpers for ideas and the timeline: labels, due dates, day grouping and where things link to. */
import type { EventRecord, IdeaKind, TimelineItem } from "@nexus/schemas";

export const KIND_LABEL: Record<IdeaKind, string> = { idea: "Idea", note: "Note", todo: "To-do" };
export const KIND_PLURAL: Record<IdeaKind, string> = { idea: "Ideas", note: "Notes", todo: "To-dos" };

const DAY_MS = 24 * 3600 * 1000;

/** Quick capture: "todo: buy soil" is a to-do, "note: …" a note, anything else an idea. */
export function parseQuickCapture(input: string): { kind: IdeaKind; text: string } {
  const m = /^(todo|to-do|note|idea)\s*:\s*/i.exec(input);
  if (!m) return { kind: "idea", text: input };
  const word = (m[1] ?? "").toLowerCase();
  return { kind: word.startsWith("to") ? "todo" : word === "note" ? "note" : "idea", text: input.slice(m[0].length) };
}

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function dayDiff(then: Date, now: Date): number {
  return Math.round((startOfDay(then).getTime() - startOfDay(now).getTime()) / DAY_MS);
}

function clock(d: Date): string {
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

/** "Today 18:00", "Tomorrow 09:00", "Friday 09:00", "12 Oct 09:00", with "Overdue" when it has passed. */
export function dueLabel(iso: string, now: Date = new Date()): { text: string; tone: "danger" | "warning" | "neutral" } {
  const due = new Date(iso);
  const days = dayDiff(due, now);
  let when: string;
  if (days === 0) when = `Today ${clock(due)}`;
  else if (days === 1) when = `Tomorrow ${clock(due)}`;
  else if (days === -1) when = `Yesterday ${clock(due)}`;
  else if (days > 1 && days < 7) when = `${due.toLocaleDateString([], { weekday: "long" })} ${clock(due)}`;
  else when = `${due.toLocaleDateString([], { day: "numeric", month: "short" })} ${clock(due)}`;
  if (due.getTime() <= now.getTime()) return { text: `Overdue · ${when}`, tone: "danger" };
  return { text: when, tone: days === 0 ? "warning" : "neutral" };
}

/** Quick due times: this evening (or in an hour, if it is already evening), tomorrow morning, next Monday. */
export function duePresets(now: Date = new Date()): { id: string; label: string; at: Date }[] {
  const evening = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 18, 0);
  const later = now.getHours() >= 17 ? new Date(now.getTime() + 3600 * 1000) : evening;
  later.setSeconds(0, 0);
  const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 9, 0);
  const toMonday = ((8 - now.getDay()) % 7) || 7;
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() + toMonday, 9, 0);
  return [
    { id: "later", label: now.getHours() >= 17 ? "In an hour" : "This evening", at: later },
    { id: "tomorrow", label: "Tomorrow morning", at: tomorrow },
    { id: "next-week", label: "Next Monday", at: monday },
  ];
}

/** `<input type="datetime-local">` speaks local wall-clock time without a zone; the API wants an instant. */
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function fromLocalInput(value: string): string | null {
  if (!value) return null;
  const d = new Date(value); // "YYYY-MM-DDTHH:mm" is read as local time
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

/** "Today", "Yesterday", or "Monday 28 September" (with the year when it is not this year). */
export function dayLabel(iso: string, now: Date = new Date()): string {
  const d = new Date(iso);
  const days = dayDiff(d, now);
  if (days === 0) return "Today";
  if (days === -1) return "Yesterday";
  const sameYear = d.getFullYear() === now.getFullYear();
  return d.toLocaleDateString([], { weekday: "long", day: "numeric", month: "long", ...(sameYear ? {} : { year: "numeric" }) });
}

/** Group newest-first events by local day, keeping their order. */
export function groupByDay(events: EventRecord[], now: Date = new Date()): { day: string; events: EventRecord[] }[] {
  const groups: { day: string; events: EventRecord[] }[] = [];
  for (const e of events) {
    const day = dayLabel(e.ts, now);
    const last = groups[groups.length - 1];
    if (last && last.day === day) last.events.push(e);
    else groups.push({ day, events: [e] });
  }
  return groups;
}

export function timelineHref(item: Pick<TimelineItem, "kind" | "id" | "ref_id">): string {
  switch (item.kind) {
    case "objective":
      return `/objectives/${item.id}`;
    case "agent_run":
      return `/runs/${item.id}`;
    case "workflow_run":
      return `/workflow-runs/${item.id}`;
    case "schedule":
      return item.ref_id ? `/workflows/${item.ref_id}` : "/workflows";
    case "approval":
      return "/approvals";
    case "idea":
      return `/ideas?idea=${item.id}`;
  }
}

const str = (v: unknown): string | undefined => (typeof v === "string" && v ? v : undefined);

/** Where an event in the history leads, if anywhere: the most specific thing it is about. */
export function eventHref(e: EventRecord): string | undefined {
  const p = e.payload;
  if (e.type.startsWith("IDEA_")) return e.type === "IDEA_DELETED" ? "/ideas" : `/ideas?idea=${str(p["idea_id"]) ?? ""}`;
  if (e.type.startsWith("APPROVAL_")) return "/approvals";
  if (e.objective_id) return `/objectives/${e.objective_id}`;
  if (e.run_id) return `/runs/${e.run_id}`;
  const workflowRun = str(p["workflow_run_id"]);
  if (workflowRun) return `/workflow-runs/${workflowRun}`;
  const workflow = str(p["workflow_id"]);
  if (workflow && e.type !== "WORKFLOW_DELETED") return `/workflows/${workflow}`;
  if (e.type.startsWith("MCP_")) return "/settings/integrations";
  if (e.type.startsWith("MEMORY_")) return "/memory";
  if (e.project_id && e.type.startsWith("PROJECT_")) return `/projects/${e.project_id}`;
  return undefined;
}
