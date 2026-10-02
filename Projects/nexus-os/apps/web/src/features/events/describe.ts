import type { EventRecord } from "@nexus/schemas";
import { MESSAGE_LABEL, agentName, messageText } from "../objectives/format";

export type Tone = "neutral" | "accent" | "success" | "warning" | "danger" | "info";

export interface EventView {
  text: string;
  tone: Tone;
}

const str = (v: unknown): string | undefined => (typeof v === "string" && v ? v : undefined);
const num = (v: unknown): string => (typeof v === "number" ? String(v) : "?");
const agent = (v: unknown): string => (typeof v === "string" && v ? agentName(v) : "an agent");
const capital = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1);
const IDEA_KIND: Record<string, string> = { idea: "Idea", note: "Note", todo: "To-do" };
const ideaKind = (p: Record<string, unknown>): string => IDEA_KIND[str(p["kind"]) ?? ""] ?? "Idea";
const taskName = (p: Record<string, unknown>): string => {
  const title = str(p["title"]);
  return title ? `“${title}”` : (str(p["key"]) ?? "a task");
};

function messageView(sender: string, recipient: string, type: string, payload: unknown): EventView {
  const known = type in MESSAGE_LABEL;
  const text = known ? messageText({ type: type as keyof typeof MESSAGE_LABEL, payload: (payload ?? {}) as Record<string, unknown> }) : "";
  const verb = known ? MESSAGE_LABEL[type as keyof typeof MESSAGE_LABEL] : "sent a message";
  const to = recipient && recipient !== "orchestrator" ? ` ${agentName(recipient)}` : "";
  return {
    text: `${capital(agentName(sender))} ${verb}${to}${text ? `: ${text}` : ""}`,
    tone: type === "QUESTION" ? "warning" : type === "ERROR" ? "danger" : "neutral",
  };
}

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
    case "AGENT_MESSAGE": {
      // Orchestrated runs record structured hand-offs; a lone run records a question for the person.
      const sender = str(p["sender"]);
      if (!sender) return { text: `Agent asks: ${str(p["text"]) ?? "a question"}`, tone: "warning" };
      const view = messageView(sender, str(p["recipient"]) ?? "", str(p["type"]) ?? "", p["payload"]);
      return view;
    }
    case "OBJECTIVE_CREATED":
      return { text: `New objective: ${str(p["text"]) ?? ""}`, tone: "accent" };
    case "OBJECTIVE_STARTED":
      return { text: p["phase"] === "planning" ? "Planning the objective" : "Working on the objective", tone: "accent" };
    case "PLAN_CREATED": {
      const n = Number(p["tasks"] ?? 0);
      return { text: `Plan ready: ${n} ${n === 1 ? "task" : "tasks"}`, tone: "info" };
    }
    case "PLAN_EDITED":
      return { text: "Plan edited", tone: "neutral" };
    case "PLAN_APPROVED":
      return { text: p["mode"] === "safe_only" ? "Plan approved (safe steps only)" : "Plan approved", tone: "success" };
    case "OBJECTIVE_PAUSED":
      return { text: `Objective waiting for you${str(p["reason"]) ? `: ${str(p["reason"])}` : ""}`, tone: "warning" };
    case "OBJECTIVE_RESUMED":
      return { text: "Objective resumed", tone: "accent" };
    case "OBJECTIVE_COMPLETED":
      return {
        text: p["verdict"] === "PASS" ? "Objective complete and verified" : `Objective finished: ${String(p["verdict"] ?? p["status"] ?? "").toLowerCase()}`,
        tone: p["verdict"] === "PASS" ? "success" : "warning",
      };
    case "OBJECTIVE_FAILED":
      return { text: `Objective not achieved${str(p["summary"]) || str(p["message"]) ? `: ${str(p["summary"]) ?? str(p["message"])}` : ""}`, tone: "danger" };
    case "OBJECTIVE_CANCELLED":
      return { text: "Objective cancelled", tone: "warning" };
    case "TASK_CREATED":
      return { text: `Task ${taskName(p)} added for ${agent(p["agent"])}`, tone: "neutral" };
    case "TASK_STARTED":
      return { text: `${capital(agent(p["agent"]))} started ${taskName(p)}`, tone: "accent" };
    case "TASK_COMPLETED":
      return { text: `${capital(agent(p["agent"]))} finished ${taskName(p)}`, tone: "success" };
    case "TASK_FAILED":
      return { text: `Task ${taskName(p)} failed`, tone: "danger" };
    case "TASK_BLOCKED":
      return { text: `Task ${taskName(p)} needs you`, tone: "warning" };
    case "TASK_CANCELLED":
      return { text: `Task ${taskName(p)} cancelled`, tone: "neutral" };
    case "TASK_RETRIED":
      return { text: `${p["action"] === "resume" ? "Resuming" : "Retrying"} ${taskName(p)}`, tone: "info" };
    case "TASK_STATUS_CHANGED":
      return { text: `Task ${taskName(p)}: ${String(p["status"] ?? "").toLowerCase().replaceAll("_", " ")}`, tone: "neutral" };
    case "REVIEW_COMPLETED": {
      const approve = p["verdict"] === "approve";
      return { text: `Critic ${approve ? "approved" : "asked for changes to"} ${taskName(p)}`, tone: approve ? "success" : "warning" };
    }
    case "VERIFICATION_COMPLETED":
      return {
        text: `Verifier: ${String(p["verdict"] ?? "?")}${str(p["summary"]) ? `, ${str(p["summary"])}` : ""}`,
        tone: p["verdict"] === "PASS" ? "success" : p["verdict"] === "FAIL" ? "danger" : "warning",
      };
    case "RECOVERY_DECISION":
      return { text: `Recovery for ${taskName(p)}: ${str(p["action"]) ?? "?"}${str(p["reason"]) ? `, ${str(p["reason"])}` : ""}`, tone: "info" };
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
      if (Array.isArray(p["findings"]) && p["findings"].includes("mcp_tool_definition"))
        return { text: `MCP tool ${str(p["tool"]) ?? ""} switched off until you review it`, tone: "warning" };
      return { text: `Instruction-like text found in ${str(p["source"]) ?? "outside content"}; treated as data`, tone: "warning" };
    case "MCP_SERVER_ADDED":
      return { text: `MCP server added: ${str(p["name"]) ?? ""}`, tone: "info" };
    case "MCP_SERVER_UPDATED":
      return { text: `MCP server ${str(p["name"]) ?? ""} settings changed`, tone: "info" };
    case "MCP_SERVER_REMOVED":
      return { text: `MCP server removed: ${str(p["name"]) ?? ""}`, tone: "warning" };
    case "MCP_SERVER_STARTED":
      return { text: `MCP server ${str(p["name"]) ?? ""} connected (${num(p["tools"])} tools)`, tone: "success" };
    case "MCP_SERVER_STOPPED":
      return { text: `MCP server ${str(p["name"]) ?? ""} stopped`, tone: "neutral" };
    case "MCP_SERVER_FAILED":
      return { text: `MCP server ${str(p["name"]) ?? ""} is not working: ${str(p["message"]) ?? "unknown problem"}`, tone: "danger" };
    case "MCP_TOOLS_CHANGED":
      return { text: `MCP server ${str(p["name"]) ?? ""} changed its tools (${num(p["tools"])} now)`, tone: "info" };
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
    case "MEMORY_CREATED":
      return {
        text: `${p["status"] === "pending" ? "Suggested remembering" : "Remembered"}: ${str(p["preview"]) ?? "a note"}`,
        tone: p["status"] === "pending" ? "warning" : "info",
      };
    case "MEMORY_UPDATED": {
      const change = str(p["change"]) ?? "edited";
      const verb = { confirmed: "Kept", restored: "Restored", merged: "Merged into an existing memory", edited: "Edited" }[change] ?? "Updated";
      return { text: `${verb}: ${str(p["preview"]) ?? "a memory"}`, tone: change === "confirmed" ? "success" : "neutral" };
    }
    case "MEMORY_DELETED":
      return {
        text: p["reason"] === "purged" ? "A memory was erased" : p["reason"] === "dismissed" ? "Memory suggestion dismissed" : "A memory was deleted",
        tone: "neutral",
      };
    case "MEMORY_REJECTED": {
      const cats = Array.isArray(p["categories"]) ? (p["categories"] as string[]).join(", ") : "sensitive data";
      return { text: `Not remembered: it looked like it contained ${cats}`, tone: "warning" };
    }
    case "MEMORY_COMPRESSED":
      return { text: `Folded ${String(p["merged"] ?? "some")} older notes into one summary`, tone: "info" };
    case "WORKFLOW_CREATED":
      return { text: `Workflow created: ${str(p["name"]) ?? ""}`, tone: "neutral" };
    case "WORKFLOW_UPDATED":
      return { text: p["new_version"] === true ? `Workflow saved as version ${String(p["version"])}: ${str(p["name"]) ?? ""}` : `Workflow updated: ${str(p["name"]) ?? ""}`, tone: "neutral" };
    case "WORKFLOW_DELETED":
      return { text: `Workflow deleted: ${str(p["name"]) ?? ""}`, tone: "warning" };
    case "WORKFLOW_STARTED":
      return { text: `${p["scheduled"] === true ? "Scheduled run" : "Run"} of ${str(p["name"]) ?? "a workflow"} started`, tone: "accent" };
    case "WORKFLOW_NODE_STARTED":
      return { text: `${str(p["name"]) ?? "Workflow"}: ${str(p["label"]) ?? str(p["node"]) ?? "a step"} started`, tone: "neutral" };
    case "WORKFLOW_NODE_COMPLETED":
      return {
        text: `${str(p["name"]) ?? "Workflow"}: ${str(p["label"]) ?? str(p["node"]) ?? "a step"} ${p["approved"] === false ? "rejected" : p["approved"] === true ? "approved" : "done"}`,
        tone: p["approved"] === false ? "warning" : "success",
      };
    case "WORKFLOW_NODE_FAILED":
      return { text: `${str(p["name"]) ?? "Workflow"}: ${str(p["label"]) ?? str(p["node"]) ?? "a step"} failed${str(p["message"]) ? `: ${str(p["message"])}` : ""}`, tone: "danger" };
    case "WORKFLOW_WAITING":
      return { text: `${str(p["name"]) ?? "A workflow"} is waiting for you`, tone: "warning" };
    case "WORKFLOW_COMPLETED":
      return { text: `${str(p["name"]) ?? "Workflow"} finished`, tone: "success" };
    case "WORKFLOW_FAILED":
      return { text: `${str(p["name"]) ?? "Workflow"} failed${str(p["message"]) ? `: ${str(p["message"])}` : ""}`, tone: "danger" };
    case "WORKFLOW_CANCELLED":
      return { text: `${str(p["name"]) ?? "Workflow"} run cancelled`, tone: "warning" };
    case "SCHEDULE_CREATED":
      return { text: `Scheduled: ${str(p["description"]) ?? str(p["cron"]) ?? ""}`, tone: "info" };
    case "SCHEDULE_UPDATED":
      return { text: p["enabled"] === false ? "Schedule turned off" : "Schedule updated", tone: "neutral" };
    case "SCHEDULE_DELETED":
      return { text: "Schedule deleted", tone: "neutral" };
    case "SCHEDULE_FIRED":
      return { text: p["manual"] === true ? "Scheduled workflow run by hand" : "Schedule started a workflow run", tone: "accent" };
    case "SCHEDULE_SKIPPED":
      return { text: `Scheduled run skipped: ${str(p["reason"]) ?? ""}`, tone: "warning" };
    case "IDEA_CREATED":
      return { text: `${ideaKind(p)} added: ${str(p["text"]) ?? ""}`, tone: "info" };
    case "IDEA_UPDATED": {
      const changed = Array.isArray(p["changed"]) ? (p["changed"] as unknown[]) : [];
      if (str(p["objective_id"])) return { text: `Started as an objective: ${str(p["text"]) ?? ""}`, tone: "accent" };
      if (changed.includes("status")) {
        const done = p["status"] === "done";
        return { text: `${ideaKind(p)} ${done ? "done" : "reopened"}: ${str(p["text"]) ?? ""}`, tone: done ? "success" : "neutral" };
      }
      if (changed.length === 1 && changed[0] === "pinned") {
        return { text: `${ideaKind(p)} ${p["pinned"] === true ? "pinned" : "unpinned"}: ${str(p["text"]) ?? ""}`, tone: "neutral" };
      }
      return { text: `${ideaKind(p)} edited: ${str(p["text"]) ?? ""}`, tone: "neutral" };
    }
    case "IDEA_DELETED":
      return { text: `${ideaKind(p)} deleted: ${str(p["text"]) ?? ""}`, tone: "neutral" };
    case "IDEA_DUE":
      return { text: `${ideaKind(p)} due: ${str(p["text"]) ?? ""}`, tone: "warning" };
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
