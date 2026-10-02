import type { Agent, AgentRun, RiskLevel, RunStatus, ToolCall } from "@nexus/schemas";
import type { Tone } from "../events/describe";

export interface RunStatusView {
  label: string;
  tone: Tone;
  live: boolean; // still working or waiting on someone
}

export const RUN_STATUS: Record<RunStatus, RunStatusView> = {
  RUNNING: { label: "Working", tone: "accent", live: true },
  WAITING_APPROVAL: { label: "Needs approval", tone: "warning", live: true },
  WAITING_INPUT: { label: "Has a question", tone: "warning", live: true },
  COMPLETED: { label: "Completed", tone: "success", live: false },
  FAILED: { label: "Failed", tone: "danger", live: false },
  CANCELLED: { label: "Cancelled", tone: "neutral", live: false },
  TIMED_OUT: { label: "Timed out", tone: "danger", live: false },
  INTERRUPTED: { label: "Interrupted", tone: "warning", live: false },
};

export const RISK: Record<RiskLevel, { label: string; tone: Tone; meaning: string }> = {
  SAFE: { label: "Safe", tone: "success", meaning: "Reads or computes; changes nothing." },
  MODERATE: { label: "Moderate", tone: "info", meaning: "Changes project files or fetches from the web." },
  HIGH: { label: "High", tone: "warning", meaning: "Runs code, deletes, or has wider reach." },
  VERY_HIGH: { label: "Very high", tone: "danger", meaning: "Network-enabled commands or system-level effects." },
};

export const TOOL_STATUS: Record<ToolCall["status"], { label: string; tone: Tone }> = {
  PROPOSED: { label: "Proposed", tone: "neutral" },
  AWAITING_APPROVAL: { label: "Awaiting approval", tone: "warning" },
  RUNNING: { label: "Running", tone: "accent" },
  SUCCEEDED: { label: "Succeeded", tone: "success" },
  FAILED: { label: "Failed", tone: "danger" },
  DENIED: { label: "Denied", tone: "danger" },
};

export const RISK_ORDER: RiskLevel[] = ["SAFE", "MODERATE", "HIGH", "VERY_HIGH"];

/** The API omits fields that hold their defaults; the UI always wants a complete agent. */
export interface AgentView {
  id: string;
  slug: string;
  name: string;
  role: string;
  description: string;
  icon: string;
  color: string;
  systemPrompt: string;
  preferredModel: string | null;
  tools: string[];
  maxRisk: RiskLevel;
  maxSteps: number;
  maxRuntimeS: number;
  maxToolCalls: number;
  tokenBudget: number;
  temperature: number;
  status: "idle" | "busy" | "disabled";
  builtin: boolean;
}

export function normalizeAgent(a: Agent): AgentView {
  return {
    id: a.id,
    slug: a.slug,
    name: a.name,
    role: a.role,
    description: a.description ?? "",
    icon: a.icon ?? "bot",
    color: a.color ?? "",
    systemPrompt: a.system_prompt ?? "",
    preferredModel: a.preferred_model ?? null,
    tools: a.tools ?? [],
    maxRisk: a.permissions?.max_risk ?? "MODERATE",
    maxSteps: a.max_steps ?? 20,
    maxRuntimeS: a.max_runtime_s ?? 300,
    maxToolCalls: a.max_tool_calls ?? 40,
    tokenBudget: a.token_budget ?? 200_000,
    temperature: a.temperature ?? 0.2,
    status: a.status ?? "idle",
    builtin: a.builtin ?? false,
  };
}

/** Does an allow-list entry (exact name or ``prefix*``) cover this tool? */
export function toolMatches(pattern: string, name: string): boolean {
  return pattern.endsWith("*") ? name.startsWith(pattern.slice(0, -1)) : pattern === name;
}

export function agentCanUse(agent: Pick<AgentView, "tools">, tool: string): boolean {
  return agent.tools.some((p) => toolMatches(p, tool));
}

// ---- steps: the stored checkpoint, parsed defensively -------------------------------------

export interface StepView {
  n: number;
  summary: string;
  kind: "tool_call" | "finish" | "ask_human" | "unknown";
  tool?: string;
  args: [string, string][];
  question?: string;
  resultStatus?: string;
  resultSummary?: string;
  observation?: { status: string; text: string; flags: string[]; errorCode?: string; untrusted: boolean };
  notes: string[];
}

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const asString = (v: unknown): string | undefined => (typeof v === "string" ? v : undefined);
const strings = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

export function clip(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, max)}… (${(text.length - max).toLocaleString()} more characters)`;
}

export function prettyArgs(args: unknown, max = 400): [string, string][] {
  if (!isRecord(args)) return [];
  return Object.entries(args).map(([k, v]) => [k, clip(typeof v === "string" ? v : JSON.stringify(v), max)]);
}

export function parseStep(raw: unknown): StepView | null {
  if (!isRecord(raw) || !isRecord(raw["action"])) return null;
  const action = raw["action"];
  const type = asString(action["type"]);
  const kind: StepView["kind"] = type === "tool_call" || type === "finish" || type === "ask_human" ? type : "unknown";
  const obs = isRecord(raw["observation"]) ? raw["observation"] : undefined;
  const result = isRecord(action["result"]) ? action["result"] : undefined;
  const step: StepView = {
    n: typeof raw["n"] === "number" ? raw["n"] : 0,
    summary: asString(raw["summary"]) ?? "",
    kind,
    args: kind === "tool_call" ? prettyArgs(action["arguments"]) : [],
    notes: strings(raw["notes"]),
  };
  const tool = asString(action["tool"]);
  if (tool) step.tool = tool;
  const question = asString(action["question"]);
  if (question) step.question = question;
  const rs = result ? asString(result["status"]) : undefined;
  if (rs) step.resultStatus = rs;
  const rsum = result ? asString(result["summary"]) : undefined;
  if (rsum) step.resultSummary = rsum;
  if (obs) {
    const code = asString(obs["error_code"]);
    step.observation = {
      status: asString(obs["status"]) ?? "ok",
      text: asString(obs["text"]) ?? "",
      flags: strings(obs["flags"]),
      untrusted: obs["untrusted"] === true,
      ...(code ? { errorCode: code } : {}),
    };
  }
  return step;
}

export function stepHeadline(s: StepView): string {
  switch (s.kind) {
    case "tool_call":
      return `Used ${s.tool ?? "a tool"}`;
    case "finish":
      return s.resultStatus === "failed" ? "Reported it could not finish" : "Finished";
    case "ask_human":
      return "Asked you a question";
    default:
      return "Step";
  }
}

/** Show JSON results readably; leave anything else alone. */
export function formatToolText(text: string): string {
  const t = text.trim();
  if (!(t.startsWith("{") || t.startsWith("["))) return text;
  try {
    return JSON.stringify(JSON.parse(t), null, 2);
  } catch {
    return text;
  }
}

export function runDuration(run: Pick<AgentRun, "started_at" | "finished_at">, now = new Date()): number {
  const end = run.finished_at ? new Date(run.finished_at) : now;
  return Math.max(0, (end.getTime() - new Date(run.started_at).getTime()) / 1000);
}

export function totalTokens(run: Pick<AgentRun, "tokens_in" | "tokens_out">): number {
  return run.tokens_in + run.tokens_out;
}

/** Editing arguments: parse what a person typed, and say what is wrong if it is not a JSON object. */
export function parseArgumentsJson(
  text: string,
): { ok: true; value: Record<string, unknown> } | { ok: false; error: string } {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch (e) {
    return { ok: false, error: e instanceof Error ? `That is not valid JSON (${e.message}).` : "That is not valid JSON." };
  }
  if (!isRecord(value)) {
    return { ok: false, error: 'The arguments must be a JSON object, like {"path": "files/a.txt"}.' };
  }
  return { ok: true, value };
}
