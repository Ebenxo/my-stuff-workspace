import type { EventRecord } from "@nexus/schemas";

export type Tone = "neutral" | "accent" | "success" | "warning" | "danger" | "info";

export interface EventView {
  text: string;
  tone: Tone;
}

const str = (v: unknown): string | undefined => (typeof v === "string" && v ? v : undefined);

/**
 * Human summaries for the Activity panel. Only actions, statuses and decisions are shown;
 * agents' private reasoning is never part of an event payload.
 */
export function describeEvent(e: EventRecord): EventView {
  const p = e.payload;
  switch (e.type) {
    case "SYSTEM_STARTED":
      return { text: `NEXUS started (v${str(p["version"]) ?? "?"})`, tone: "neutral" };
    case "SYSTEM_ERROR":
      return { text: `System error${str(p["message"]) ? `: ${str(p["message"])}` : ""}`, tone: "danger" };
    case "SETTINGS_UPDATED": {
      const changed = Array.isArray(p["changed"]) ? (p["changed"] as string[]).join(", ") : "settings";
      return { text: `Settings updated (${changed})`, tone: "neutral" };
    }
    case "PROJECT_CREATED":
      return { text: `Project created: ${str(p["name"]) ?? e.project_id ?? ""}`, tone: "success" };
    case "PROJECT_UPDATED":
      return { text: "Project updated", tone: "neutral" };
    case "PROJECT_ARCHIVED":
      return { text: "Project archived", tone: "warning" };
    case "CONVERSATION_CREATED":
      return { text: `Conversation created: ${str(p["title"]) ?? ""}`, tone: "neutral" };
    case "MESSAGE_CREATED":
      return { text: `${str(p["role"]) ?? "user"} message added`, tone: "neutral" };
    case "NOTIFICATION_CREATED":
      return { text: str(p["title"]) ?? "Notification", tone: "info" };
    case "AGENT_STARTED":
      return { text: `${str(p["name"]) ?? "An agent"} started: ${str(p["prompt"]) ?? "a task"}`, tone: "accent" };
    case "AGENT_STEP":
      return { text: `Step ${String(p["n"] ?? "?")}: ${str(p["summary"]) ?? "working"}`, tone: "neutral" };
    case "AGENT_COMPLETED":
      return { text: `Agent finished: ${str(p["summary"]) ?? "done"}`, tone: "success" };
    case "AGENT_FAILED":
      return { text: `Agent stopped: ${str(p["message"]) ?? "it did not finish"}`, tone: "danger" };
    case "AGENT_CANCELLED":
      return { text: "Agent run cancelled", tone: "warning" };
    case "AGENT_INTERRUPTED":
      return { text: "Agent run interrupted; it can be resumed", tone: "warning" };
    case "AGENT_RESUMED":
      return { text: "Agent run resumed", tone: "accent" };
    case "AGENT_MESSAGE":
      return { text: `Agent asks: ${str(p["text"]) ?? "a question"}`, tone: "warning" };
    case "TOOL_CALLED":
      return { text: `Tool: ${str(p["tool"]) ?? "?"} (${(str(p["risk"]) ?? "?").toLowerCase()} risk)`, tone: "neutral" };
    case "TOOL_COMPLETED":
      return { text: `${str(p["tool"]) ?? "Tool"} finished`, tone: "success" };
    case "TOOL_FAILED":
      return { text: `${str(p["tool"]) ?? "Tool"} failed${str(p["code"]) ? ` (${str(p["code"])})` : ""}`, tone: "danger" };
    case "TOOL_DENIED":
      return { text: `${str(p["tool"]) ?? "Tool"} was refused${str(p["reason"]) ? `: ${str(p["reason"])}` : ""}`, tone: "danger" };
    case "POLICY_DENIED":
      return { text: `Blocked by policy: ${str(p["tool"]) ?? "an action"}`, tone: "danger" };
    case "SECURITY_FLAG":
      return { text: `Instruction-like text found in ${str(p["source"]) ?? "outside content"}; treated as data`, tone: "warning" };
    case "APPROVAL_REQUIRED":
      return { text: `Approval needed: ${str(p["tool"]) ?? "an action"}`, tone: "warning" };
    case "APPROVAL_GRANTED":
      return { text: `Approved: ${str(p["tool"]) ?? "an action"}`, tone: "success" };
    case "APPROVAL_DENIED":
      return { text: `Denied: ${str(p["tool"]) ?? "an action"}`, tone: "danger" };
    case "APPROVAL_EDITED":
      return { text: `Edited before approving: ${str(p["tool"]) ?? "an action"}`, tone: "info" };
    case "ARTIFACT_CREATED":
      return { text: `Saved ${str(p["name"]) ?? "a deliverable"}`, tone: "success" };
    case "ARTIFACT_UPDATED":
      return { text: `Updated ${str(p["name"]) ?? "a deliverable"} to v${String(p["version"] ?? "?")}`, tone: "success" };
    case "FILE_WRITTEN":
      return { text: `${p["created"] === true ? "Created" : "Updated"} ${str(p["path"]) ?? "a file"}`, tone: "neutral" };
    case "FILE_DELETED":
      return { text: `Moved ${str(p["path"]) ?? "a file"} to trash`, tone: "warning" };
    case "CLIPBOARD_REQUEST":
      return { text: `Copy offered: ${str(p["label"]) ?? "text"}`, tone: "info" };
    default:
      return {
        text: e.type.toLowerCase().replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase()),
        tone: e.type.includes("FAILED") || e.type.includes("DENIED") || e.type.includes("ERROR")
          ? "danger"
          : e.type.includes("COMPLETED") || e.type.includes("GRANTED")
            ? "success"
            : e.type.includes("REQUIRED")
              ? "warning"
              : "neutral",
      };
  }
}

/**
 * Events that belong in the raw Events log but not in human-facing activity feeds: notifications
 * repeat an event already shown (and live in the bell), and usage is bookkeeping for every model call.
 */
const BOOKKEEPING = new Set(["NOTIFICATION_CREATED", "USAGE_RECORDED"]);
export const isActivityEvent = (e: EventRecord): boolean => !BOOKKEEPING.has(e.type);

export const isErrorEvent = (e: EventRecord): boolean =>
  /(_FAILED|_ERROR|_DENIED)$/.test(e.type) || e.type === "SECURITY_FLAG";

export function formatClock(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour12: false });
}
