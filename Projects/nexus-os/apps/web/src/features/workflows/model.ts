import type {
  NodeState,
  ValidationReport,
  WorkflowDefinition,
  WorkflowEdge,
  WorkflowInput,
  WorkflowNode,
  WorkflowNodeType,
  WorkflowRunStatus,
} from "@nexus/schemas";
import type { Tone } from "../events/describe";

export interface NodeMeta {
  label: string;
  description: string;
  /** Has 'true'/'false' outcomes (two outgoing handles). */
  branches: boolean;
  defaults: () => Record<string, unknown>;
}

export const NODE_META: Record<WorkflowNodeType, NodeMeta> = {
  trigger: { label: "Start", description: "Where every run begins. Its output is the run's inputs.", branches: false, defaults: () => ({}) },
  agent: {
    label: "Agent",
    description: "An agent works on a task. Values from other steps reach it as data, never as instructions.",
    branches: false,
    defaults: () => ({ agent: "writer", prompt: "" }),
  },
  tool: {
    label: "Tool",
    description: "Runs one tool. Risky tools wait for your approval, and scheduled runs never auto-approve them.",
    branches: false,
    defaults: () => ({ tool: "write_file", arguments: {} }),
  },
  condition: { label: "Condition", description: "Chooses a path: true or false.", branches: true, defaults: () => ({ expression: "" }) },
  approval: {
    label: "Approval",
    description: "Waits for you to approve or reject. 'Yes' follows approval, 'No' follows rejection.",
    branches: true,
    defaults: () => ({ message: "" }),
  },
  transform: { label: "Transform", description: "Computes named values from inputs and earlier steps.", branches: false, defaults: () => ({ values: {} }) },
  output: { label: "Output", description: "Sets the run's outputs.", branches: false, defaults: () => ({ values: {} }) },
  delay: { label: "Delay", description: "Waits a number of seconds.", branches: false, defaults: () => ({ seconds: 60 }) },
  loop: {
    label: "Loop",
    description: "Runs an agent or a tool once per item of a list.",
    branches: false,
    defaults: () => ({ items: "", max_items: 10, body: { type: "tool", config: { tool: "calculator", arguments: {} } } }),
  },
  subworkflow: { label: "Sub-workflow", description: "Runs another workflow of this project and returns its outputs.", branches: false, defaults: () => ({ workflow_id: "", inputs: {} }) },
};

export const ADDABLE: WorkflowNodeType[] = ["agent", "tool", "condition", "approval", "transform", "output", "delay", "loop", "subworkflow"];

export const RUN_STATUS: Record<WorkflowRunStatus, { label: string; tone: Tone }> = {
  RUNNING: { label: "Running", tone: "accent" },
  WAITING: { label: "Needs you", tone: "warning" },
  COMPLETED: { label: "Completed", tone: "success" },
  FAILED: { label: "Failed", tone: "danger" },
  CANCELLED: { label: "Cancelled", tone: "neutral" },
};

export type NodeStatus = NonNullable<NodeState["status"]>;
export const NODE_STATUS: Record<NodeStatus, { label: string; tone: Tone }> = {
  PENDING: { label: "Not started", tone: "neutral" },
  RUNNING: { label: "Running", tone: "accent" },
  WAITING: { label: "Needs you", tone: "warning" },
  COMPLETED: { label: "Done", tone: "success" },
  SKIPPED: { label: "Skipped", tone: "neutral" },
  FAILED: { label: "Failed", tone: "danger" },
  CANCELLED: { label: "Cancelled", tone: "neutral" },
};

// ---- editing the graph (pure; every function returns a new definition) ---------------------------

export function nextNodeId(type: WorkflowNodeType, nodes: WorkflowNode[]): string {
  const taken = new Set(nodes.map((n) => n.id));
  for (let i = 1; ; i++) {
    const id = `${type}_${i}`;
    if (!taken.has(id)) return id;
  }
}

export function addNode(def: WorkflowDefinition, type: WorkflowNodeType, position: { x: number; y: number }): { def: WorkflowDefinition; id: string } {
  const nodes = def.nodes ?? [];
  const id = nextNodeId(type, nodes);
  const node: WorkflowNode = { id, type, label: NODE_META[type].label, config: NODE_META[type].defaults(), position, continue_on_error: false };
  return { def: { ...def, nodes: [...nodes, node] }, id };
}

/** A free spot near (x, y): moves right in steps until no step sits there. */
export function placeNear(nodes: WorkflowNode[], x: number, y: number): { x: number; y: number } {
  let tx = x;
  while (nodes.some((n) => Math.abs((n.position?.x ?? 0) - tx) < 220 && Math.abs((n.position?.y ?? 0) - y) < 100)) tx += 260;
  return { x: tx, y };
}

/** Add a step after ``fromId`` (connected from it, placed below it), or at the end when nothing is selected.
 * The canvas flows top to bottom, which suits the editor's tall column and small screens. */
export function addAfter(
  def: WorkflowDefinition,
  type: WorkflowNodeType,
  fromId: string | undefined,
): { def: WorkflowDefinition; id: string } {
  const nodes = def.nodes ?? [];
  const from = nodes.find((n) => n.id === fromId);
  const pos = from
    ? placeNear(nodes, from.position?.x ?? 0, (from.position?.y ?? 0) + 150)
    : placeNear(nodes, 0, Math.max(0, ...nodes.map((n) => n.position?.y ?? 0)) + 150);
  const added = addNode(def, type, pos);
  if (!from) return added;
  const linked = connect(added.def, from.id, added.id, NODE_META[from.type].branches ? "true" : null);
  return "def" in linked ? { def: linked.def, id: added.id } : added;
}

export function updateNode(def: WorkflowDefinition, id: string, patch: Partial<WorkflowNode>): WorkflowDefinition {
  return { ...def, nodes: (def.nodes ?? []).map((n) => (n.id === id ? { ...n, ...patch } : n)) };
}

export function removeNode(def: WorkflowDefinition, id: string): WorkflowDefinition {
  return {
    ...def,
    nodes: (def.nodes ?? []).filter((n) => n.id !== id || n.type === "trigger"),
    edges: (def.edges ?? []).filter((e) => e.source !== id && e.target !== id),
  };
}

export function removeEdge(def: WorkflowDefinition, edgeId: string): WorkflowDefinition {
  return { ...def, edges: (def.edges ?? []).filter((e) => e.id !== edgeId) };
}

function reaches(edges: WorkflowEdge[], from: string, to: string): boolean {
  const seen = new Set<string>();
  const stack = [from];
  while (stack.length) {
    const k = stack.pop()!;
    if (k === to) return true;
    if (seen.has(k)) continue;
    seen.add(k);
    for (const e of edges) if (e.source === k) stack.push(e.target);
  }
  return false;
}

/** Connect two steps, or say why not (the editor shows the reason). */
export function connect(
  def: WorkflowDefinition,
  source: string,
  target: string,
  branch?: "true" | "false" | null,
): { def: WorkflowDefinition } | { error: string } {
  const nodes = new Map((def.nodes ?? []).map((n) => [n.id, n]));
  const edges = def.edges ?? [];
  const src = nodes.get(source);
  const dst = nodes.get(target);
  if (!src || !dst) return { error: "Both steps must exist." };
  if (source === target) return { error: "A step cannot connect to itself." };
  if (dst.type === "trigger") return { error: "Nothing can lead into the start." };
  const branching = NODE_META[src.type].branches;
  const b = branching ? (branch ?? "true") : null;
  if (edges.some((e) => e.source === source && e.target === target && (e.branch ?? null) === b)) return { error: "Already connected." };
  if (reaches(edges, target, source)) return { error: "That would make a loop. Use a Loop step to repeat work." };
  const edge: WorkflowEdge = { id: `${source}-${target}${b ? `-${b}` : ""}`, source, target, ...(b ? { branch: b } : {}) };
  return { def: { ...def, edges: [...edges, edge] } };
}

// ---- reading ---------------------------------------------------------------------------------------

const str = (v: unknown): string => (typeof v === "string" ? v : "");

/** One line describing what a step does, for its card on the canvas. */
export function summarize(node: WorkflowNode): string {
  const c = node.config ?? {};
  switch (node.type) {
    case "trigger":
      return "Runs with the inputs you give it";
    case "agent":
      return `${str(c["agent"]).replaceAll("_", " ") || "agent"}: ${str(c["prompt"]) || "no task yet"}`;
    case "tool":
      return str(c["tool"]) || "no tool chosen";
    case "condition":
      return str(c["expression"]) || "no condition yet";
    case "approval":
      return str(c["message"]) || "asks you before continuing";
    case "transform":
    case "output": {
      const keys = Object.keys((c["values"] as Record<string, unknown> | undefined) ?? {});
      return keys.length ? keys.join(", ") : "no values yet";
    }
    case "delay":
      return `wait ${typeof c["seconds"] === "number" ? formatSeconds(c["seconds"]) : "?"}`;
    case "loop":
      return `for each item of ${str(c["items"]) || "…"}`;
    case "subworkflow":
      return str(c["workflow_id"]) ? "runs another workflow" : "no workflow chosen";
  }
}

export function formatSeconds(s: number): string {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.round(s / 60)} min`;
  return `${(s / 3600).toFixed(s % 3600 ? 1 : 0)} h`;
}

export function issuesByNode(report: ValidationReport | undefined): { byNode: Map<string, string[]>; general: string[] } {
  const byNode = new Map<string, string[]>();
  const general: string[] = [];
  for (const i of report?.issues ?? []) {
    if (i.node) byNode.set(i.node, [...(byNode.get(i.node) ?? []), i.message]);
    else general.push(i.message);
  }
  return { byNode, general };
}

// ---- inputs ----------------------------------------------------------------------------------------

export function inputDefaults(inputs: WorkflowInput[]): Record<string, string | boolean> {
  const out: Record<string, string | boolean> = {};
  for (const i of inputs) {
    const d = i.default;
    out[i.name] = i.type === "boolean" ? d === true : d == null ? "" : String(d);
  }
  return out;
}

/** What the form holds, as the API expects it (empty optional values are left out). */
export function inputValues(inputs: WorkflowInput[], form: Record<string, string | boolean>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const i of inputs) {
    const v = form[i.name];
    if (i.type === "boolean") out[i.name] = v === true;
    else if (typeof v === "string" && v.trim() !== "") out[i.name] = i.type === "number" ? Number(v) : v;
  }
  return out;
}

export function formatValue(v: unknown, limit = 4000): string {
  const text = typeof v === "string" ? v : JSON.stringify(v, null, 2) ?? "";
  return text.length > limit ? `${text.slice(0, limit)}\n…` : text;
}

/** Common schedules, offered as one-click choices. */
export const PRESETS: { label: string; cron: string }[] = [
  { label: "Every hour", cron: "0 * * * *" },
  { label: "Every day at 09:00", cron: "0 9 * * *" },
  { label: "Weekdays at 09:00", cron: "0 9 * * 1-5" },
  { label: "Every Monday at 08:00", cron: "0 8 * * 1" },
  { label: "First of the month at 07:00", cron: "0 7 1 * *" },
];
