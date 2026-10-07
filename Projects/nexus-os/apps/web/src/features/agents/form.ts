import type { AgentCreate, AgentUpdate, RiskLevel } from "@nexus/schemas";
import type { AgentView } from "./format";

export interface AgentForm {
  name: string;
  role: string;
  description: string;
  systemPrompt: string;
  preferredModel: string; // "" = automatic
  tools: string[];
  maxRisk: RiskLevel;
  maxSteps: string; // text inputs so half-typed numbers are not fought with
  maxRuntimeS: string;
  maxToolCalls: string;
  tokenBudget: string;
  temperature: string;
  enabled: boolean;
}

export const EMPTY_FORM: AgentForm = {
  name: "",
  role: "",
  description: "",
  systemPrompt: "",
  preferredModel: "",
  tools: ["list_directory", "read_file", "search_files"],
  maxRisk: "MODERATE",
  maxSteps: "20",
  maxRuntimeS: "300",
  maxToolCalls: "40",
  tokenBudget: "200000",
  temperature: "0.2",
  enabled: true,
};

export function toForm(a: AgentView): AgentForm {
  return {
    name: a.name,
    role: a.role,
    description: a.description,
    systemPrompt: a.systemPrompt,
    preferredModel: a.preferredModel ?? "",
    tools: [...a.tools],
    maxRisk: a.maxRisk,
    maxSteps: String(a.maxSteps),
    maxRuntimeS: String(a.maxRuntimeS),
    maxToolCalls: String(a.maxToolCalls),
    tokenBudget: String(a.tokenBudget),
    temperature: String(a.temperature),
    enabled: a.status !== "disabled",
  };
}

type Field = keyof AgentForm;
export type FormErrors = Partial<Record<Field, string>>;

const LIMITS: { field: Field; label: string; min: number; max: number; integer: boolean }[] = [
  { field: "maxSteps", label: "Max steps", min: 1, max: 100, integer: true },
  { field: "maxRuntimeS", label: "Max runtime", min: 10, max: 3600, integer: true },
  { field: "maxToolCalls", label: "Max tool calls", min: 0, max: 200, integer: true },
  { field: "tokenBudget", label: "Token budget", min: 1000, max: 5_000_000, integer: true },
  { field: "temperature", label: "Temperature", min: 0, max: 1, integer: false },
];

/** Built-in agents keep their identity: only tuning fields are validated for them. */
export function validateForm(f: AgentForm, builtin: boolean): FormErrors {
  const errors: FormErrors = {};
  if (!builtin) {
    if (!f.name.trim()) errors.name = "Give the agent a name.";
    else if (f.name.trim().length > 80) errors.name = "Keep the name under 80 characters.";
    if (!f.role.trim()) errors.role = "Say what this agent is for, in a few words.";
    else if (f.role.trim().length > 120) errors.role = "Keep the role under 120 characters.";
  }
  for (const { field, label, min, max, integer } of LIMITS) {
    const raw = String(f[field]).trim();
    const n = Number(raw);
    if (raw === "" || Number.isNaN(n)) errors[field] = `${label} must be a number.`;
    else if (integer && !Number.isInteger(n)) errors[field] = `${label} must be a whole number.`;
    else if (n < min || n > max) errors[field] = `${label} must be between ${min.toLocaleString()} and ${max.toLocaleString()}.`;
  }
  return errors;
}

const num = (s: string) => Number(s.trim());

export function toCreate(f: AgentForm): AgentCreate {
  return {
    name: f.name.trim(),
    role: f.role.trim(),
    description: f.description.trim(),
    system_prompt: f.systemPrompt,
    preferred_model: f.preferredModel || null,
    tools: f.tools,
    permissions: { max_risk: f.maxRisk },
    max_steps: num(f.maxSteps),
    max_runtime_s: num(f.maxRuntimeS),
    max_tool_calls: num(f.maxToolCalls),
    token_budget: num(f.tokenBudget),
    temperature: num(f.temperature),
  };
}

const sameSet = (a: string[], b: string[]) => a.length === b.length && [...a].sort().join("\0") === [...b].sort().join("\0");

/**
 * Only what changed. For a built-in agent this is limited to the fields the server lets a person
 * override, so a save can never be rejected for touching its identity or prompt.
 */
export function toUpdate(current: AgentView, f: AgentForm): AgentUpdate {
  const patch: AgentUpdate = {};
  if (!current.builtin) {
    if (f.name.trim() !== current.name) patch.name = f.name.trim();
    if (f.role.trim() !== current.role) patch.role = f.role.trim();
    if (f.description.trim() !== current.description) patch.description = f.description.trim();
    if (f.systemPrompt !== current.systemPrompt) patch.system_prompt = f.systemPrompt;
  }
  if ((f.preferredModel || null) !== current.preferredModel) patch.preferred_model = f.preferredModel || null;
  if (!sameSet(f.tools, current.tools)) patch.tools = f.tools;
  if (f.maxRisk !== current.maxRisk) patch.permissions = { max_risk: f.maxRisk };
  if (num(f.maxSteps) !== current.maxSteps) patch.max_steps = num(f.maxSteps);
  if (num(f.maxRuntimeS) !== current.maxRuntimeS) patch.max_runtime_s = num(f.maxRuntimeS);
  if (num(f.maxToolCalls) !== current.maxToolCalls) patch.max_tool_calls = num(f.maxToolCalls);
  if (num(f.tokenBudget) !== current.tokenBudget) patch.token_budget = num(f.tokenBudget);
  if (num(f.temperature) !== current.temperature) patch.temperature = num(f.temperature);
  const wasEnabled = current.status !== "disabled";
  if (f.enabled !== wasEnabled) patch.status = f.enabled ? "idle" : "disabled";
  return patch;
}

/** A tool the agent is given but whose risk exceeds the agent's ceiling can never run: say so. */
export function unusableTools(
  selected: string[],
  tools: { name: string; risk_level: RiskLevel }[],
  maxRisk: RiskLevel,
  order: RiskLevel[],
): string[] {
  const ceiling = order.indexOf(maxRisk);
  return tools
    .filter((t) => selected.some((p) => (p.endsWith("*") ? t.name.startsWith(p.slice(0, -1)) : p === t.name)))
    .filter((t) => order.indexOf(t.risk_level) > ceiling)
    .map((t) => t.name);
}
