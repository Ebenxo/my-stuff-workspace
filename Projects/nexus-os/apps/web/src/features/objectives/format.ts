import type { AgentMessage, Objective, ObjectiveStatus, TaskNode, TaskStatus } from "@nexus/schemas";
import type { Tone } from "../events/describe";

export const OBJECTIVE_STATUS: Record<ObjectiveStatus, { label: string; tone: Tone; hint: string }> = {
  RECEIVED: { label: "Understanding objective…", tone: "accent", hint: "NEXUS is reading your objective." },
  PLANNING: { label: "Planning…", tone: "accent", hint: "The Planner is breaking the objective into tasks." },
  AWAITING_PLAN_APPROVAL: { label: "Plan ready", tone: "warning", hint: "Review the plan, then run it." },
  RUNNING: { label: "Working", tone: "accent", hint: "Agents are working through the tasks." },
  VERIFYING: { label: "Verifying", tone: "accent", hint: "The Verifier is checking the deliverables." },
  PAUSED: { label: "Needs you", tone: "warning", hint: "Something is waiting for your decision." },
  COMPLETED: { label: "Complete", tone: "success", hint: "The Verifier confirmed the objective." },
  PARTIAL: { label: "Partly done", tone: "warning", hint: "Some requirements are still missing." },
  FAILED: { label: "Not achieved", tone: "danger", hint: "The objective could not be completed." },
  CANCELLED: { label: "Cancelled", tone: "neutral", hint: "Stopped by you." },
};

export const TASK_STATUS: Record<TaskStatus, { label: string; tone: Tone }> = {
  WAITING: { label: "Waiting", tone: "neutral" },
  QUEUED: { label: "Queued", tone: "neutral" },
  RUNNING: { label: "Running", tone: "accent" },
  NEEDS_APPROVAL: { label: "Needs approval", tone: "warning" },
  BLOCKED: { label: "Needs you", tone: "warning" },
  COMPLETED: { label: "Completed", tone: "success" },
  SKIPPED: { label: "Skipped", tone: "neutral" },
  FAILED: { label: "Failed", tone: "danger" },
  CANCELLED: { label: "Cancelled", tone: "neutral" },
};

export const KIND_LABEL: Record<string, string> = { work: "Task", review: "Review", revise: "Revision", verify: "Verification" };

export const isLive = (s: ObjectiveStatus) => s === "RECEIVED" || s === "PLANNING" || s === "RUNNING" || s === "VERIFYING";
export const isFinal = (s: ObjectiveStatus) => s === "COMPLETED" || s === "PARTIAL" || s === "FAILED" || s === "CANCELLED";

const rec = (v: unknown): Record<string, unknown> => (typeof v === "object" && v !== null && !Array.isArray(v) ? (v as Record<string, unknown>) : {});
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

// ---- plan ------------------------------------------------------------------------------------

export interface PlanTaskView {
  key: string;
  title: string;
  description: string;
  agent: string;
  dependsOn: string[];
  tools: string[];
  expectedOutputs: string[];
  approvalRequired: boolean;
  optional: boolean;
  review: boolean;
}

export interface PlanView {
  objective: string;
  assumptions: string[];
  constraints: string[];
  risks: string[];
  criteria: string[];
  warnings: string[];
  tasks: PlanTaskView[];
  followUps: number;
  edited: boolean;
}

export function planOf(obj: Pick<Objective, "plan">): PlanView | null {
  const p = obj.plan ? rec(obj.plan) : null;
  if (!p) return null;
  const tasks = (Array.isArray(p["tasks"]) ? p["tasks"] : []).map((raw) => {
    const t = rec(raw);
    return {
      key: str(t["key"]),
      title: str(t["title"]),
      description: str(t["description"]),
      agent: str(t["agent"]),
      dependsOn: strs(t["depends_on"]),
      tools: strs(t["tools"]),
      expectedOutputs: strs(t["expected_outputs"]),
      approvalRequired: t["approval_required"] === true,
      optional: t["optional"] === true,
      review: t["review"] === true,
    };
  });
  return {
    objective: str(p["objective"]),
    assumptions: strs(p["assumptions"]),
    constraints: strs(p["constraints"]),
    risks: strs(p["risks"]),
    criteria: strs(p["completion_criteria"]),
    warnings: strs(p["warnings"]),
    tasks,
    followUps: Array.isArray(p["follow_up"]) ? p["follow_up"].length : 0,
    edited: p["edited"] === true,
  };
}

export interface StrategyView {
  name: string;
  rationale: string;
  tokens: number;
  agents: string[];
}

export function strategyOf(obj: Pick<Objective, "strategy">): StrategyView | null {
  const s = obj.strategy ? rec(obj.strategy) : null;
  if (!s) return null;
  return {
    name: str(s["name"]).replaceAll("_", " "),
    rationale: str(s["rationale"]),
    tokens: typeof s["estimated_tokens"] === "number" ? s["estimated_tokens"] : 0,
    agents: strs(s["agents"]),
  };
}

// ---- result ------------------------------------------------------------------------------------

export interface ResultView {
  verdict: "PASS" | "PARTIAL" | "FAIL" | null;
  summary: string;
  criteria: { criterion: string; met: boolean; evidence: string }[];
  missing: string[];
  artifacts: { id: string; name: string; version: number }[];
}

export function resultOf(obj: Pick<Objective, "result">): ResultView | null {
  const r = obj.result ? rec(obj.result) : null;
  if (!r) return null;
  const v = str(r["verdict"]);
  return {
    verdict: v === "PASS" || v === "PARTIAL" || v === "FAIL" ? v : null,
    summary: str(r["summary"]),
    criteria: (Array.isArray(r["criteria"]) ? r["criteria"] : []).map((c) => {
      const x = rec(c);
      return { criterion: str(x["criterion"]), met: x["met"] === true, evidence: str(x["evidence"]) };
    }),
    missing: strs(r["missing_requirements"]),
    artifacts: (Array.isArray(r["artifacts"]) ? r["artifacts"] : []).map((a) => {
      const x = rec(a);
      return { id: str(x["artifact_id"]), name: str(x["name"]), version: typeof x["version"] === "number" ? x["version"] : 1 };
    }),
  };
}

// ---- tasks -------------------------------------------------------------------------------------

export interface TaskNeeds {
  kind: "question" | "decision" | null;
  message: string;
  options: string[];
}

/** What, if anything, a task needs from the person. */
export function needsOf(t: TaskNode): TaskNeeds {
  const e = rec(t.error);
  if (t.status === "BLOCKED" && e["code"] === "needs_input") {
    return { kind: "question", message: str(e["message"]), options: strs(e["options"]) };
  }
  if (t.status === "BLOCKED" || t.status === "FAILED") {
    return { kind: "decision", message: str(e["message"]) || "This task could not finish.", options: [] };
  }
  return { kind: null, message: "", options: [] };
}

export function taskSummary(t: TaskNode): string {
  const o = rec(t.outputs);
  return str(o["summary"]);
}

export interface Positioned {
  task: TaskNode;
  x: number;
  y: number;
  level: number;
}

/**
 * Lay the graph out left to right: a task's column is one past its deepest dependency, and rows keep
 * creation order within a column. Pure, so it is testable without rendering.
 */
export function layoutTasks(tasks: TaskNode[], colWidth = 260, rowHeight = 110): Positioned[] {
  const byId = new Map(tasks.map((t) => [t.id, t]));
  const level = new Map<string, number>();
  const visiting = new Set<string>();
  const depth = (t: TaskNode): number => {
    const known = level.get(t.id);
    if (known !== undefined) return known;
    if (visiting.has(t.id)) return 0; // a cycle cannot happen (the server validates), but never loop
    visiting.add(t.id);
    const deps = (t.depends_on ?? []).map((d) => byId.get(d)).filter((d): d is TaskNode => !!d);
    const lv = deps.length ? 1 + Math.max(...deps.map(depth)) : 0;
    visiting.delete(t.id);
    level.set(t.id, lv);
    return lv;
  };
  const rows = new Map<number, number>();
  return tasks.map((task) => {
    const lv = depth(task);
    const row = rows.get(lv) ?? 0;
    rows.set(lv, row + 1);
    return { task, x: lv * colWidth, y: row * rowHeight, level: lv };
  });
}

// ---- agent messages ----------------------------------------------------------------------------

export const MESSAGE_LABEL: Record<AgentMessage["type"], string> = {
  TASK_REQUEST: "assigned",
  TASK_RESULT: "reported",
  QUESTION: "asked",
  ERROR: "reported a problem",
  STATUS: "updated",
  REVIEW_REQUEST: "asked for a review",
  REVIEW_RESULT: "reviewed",
  APPROVAL_REQUIRED: "needs approval",
};

export const agentName = (slug: string): string =>
  slug === "user" ? "you" : slug === "orchestrator" ? "NEXUS" : slug.replaceAll("_", " ");

/** The one line a person reads for a collaboration message. Only structured fields, never reasoning. */
export function messageText(m: Pick<AgentMessage, "type" | "payload">): string {
  const p = rec(m.payload);
  switch (m.type) {
    case "TASK_REQUEST":
    case "REVIEW_REQUEST":
      return str(p["title"]);
    case "QUESTION":
      return str(p["question"]);
    case "ERROR":
      return [str(p["message"]), str(p["decision"])].filter(Boolean).join(" · ");
    case "REVIEW_RESULT": {
      const blocking = typeof p["blocking_issues"] === "number" ? p["blocking_issues"] : 0;
      const verdict = str(p["verdict"]).replaceAll("_", " ");
      return [verdict && `Verdict: ${verdict}${blocking ? ` (${blocking} to fix)` : ""}`, str(p["summary"])].filter(Boolean).join(". ");
    }
    default:
      return str(p["summary"]) || str(p["message"]) || str(p["title"]);
  }
}

export function progress(tasks: TaskNode[]): { done: number; total: number } {
  const counted = tasks.filter((t) => t.kind !== "verify");
  return { done: counted.filter((t) => t.status === "COMPLETED" || t.status === "SKIPPED").length, total: counted.length };
}
