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

export const isErrorEvent = (e: EventRecord): boolean =>
  /(_FAILED|_ERROR|_DENIED)$/.test(e.type) || e.type === "SECURITY_FLAG";

export function formatClock(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour12: false });
}
