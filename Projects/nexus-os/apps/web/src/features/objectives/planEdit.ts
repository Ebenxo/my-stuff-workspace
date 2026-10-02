import type { PlanEdit } from "@nexus/schemas";
import type { PlanTaskView } from "./format";

/** A task as the plan editor holds it. The server validates again; this gives immediate feedback. */
export interface EditTask {
  key: string;
  title: string;
  description: string;
  agent: string;
  dependsOn: string[];
  review: boolean;
  optional: boolean;
  tools: string[];
  expectedOutputs: string[];
}

export const RESERVED_AGENTS = new Set(["orchestrator", "planner", "verifier"]);
const KEY = /^[A-Za-z0-9_-]{1,24}$/;

export function fromPlan(tasks: PlanTaskView[]): EditTask[] {
  return tasks.map((t) => ({
    key: t.key,
    title: t.title,
    description: t.description,
    agent: t.agent,
    dependsOn: [...t.dependsOn],
    review: t.review,
    optional: t.optional,
    tools: [...t.tools],
    expectedOutputs: [...t.expectedOutputs],
  }));
}

export function nextKey(tasks: EditTask[]): string {
  const used = new Set(tasks.map((t) => t.key));
  let n = tasks.length + 1;
  while (used.has(`t${n}`)) n += 1;
  return `t${n}`;
}

export function blankTask(tasks: EditTask[], agent: string): EditTask {
  return { key: nextKey(tasks), title: "", description: "", agent, dependsOn: [], review: false, optional: false, tools: [], expectedOutputs: [] };
}

/** Remove a task and every reference to it, so the rest of the plan stays valid. */
export function removeTask(tasks: EditTask[], key: string): EditTask[] {
  return tasks.filter((t) => t.key !== key).map((t) => ({ ...t, dependsOn: t.dependsOn.filter((d) => d !== key) }));
}

/** Returns the keys forming a dependency cycle, or null. */
export function findCycle(tasks: EditTask[]): string[] | null {
  const deps = new Map(tasks.map((t) => [t.key, t.dependsOn]));
  const state = new Map<string, 1 | 2>();
  const path: string[] = [];
  const visit = (k: string): string[] | null => {
    if (state.get(k) === 2) return null;
    if (state.get(k) === 1) return [...path.slice(path.indexOf(k)), k];
    state.set(k, 1);
    path.push(k);
    for (const d of deps.get(k) ?? []) {
      if (!deps.has(d)) continue;
      const c = visit(d);
      if (c) return c;
    }
    path.pop();
    state.set(k, 2);
    return null;
  };
  for (const k of deps.keys()) {
    const c = visit(k);
    if (c) return c;
  }
  return null;
}

export interface PlanErrors {
  general: string[];
  byTask: Record<string, string[]>;
}

export function validatePlan(tasks: EditTask[], agents: Set<string>): PlanErrors {
  const general: string[] = [];
  const byTask: Record<string, string[]> = {};
  const add = (key: string, msg: string) => (byTask[key] ??= []).push(msg);
  if (tasks.length === 0) general.push("A plan needs at least one task.");
  if (tasks.length > 20) general.push("A plan can have at most 20 tasks.");
  const keys = tasks.map((t) => t.key);
  const seen = new Set<string>();
  for (const t of tasks) {
    if (!KEY.test(t.key)) add(t.key, "The key must be 1–24 letters, digits, dashes or underscores.");
    if (seen.has(t.key)) add(t.key, `The key "${t.key}" is used twice.`);
    seen.add(t.key);
    if (!t.title.trim()) add(t.key, "Give the task a title.");
    if (!agents.has(t.agent)) add(t.key, `"${t.agent}" is not an available agent.`);
    else if (RESERVED_AGENTS.has(t.agent)) add(t.key, `The ${t.agent} has a fixed role and cannot take plan tasks.`);
    for (const d of t.dependsOn) {
      if (d === t.key) add(t.key, "A task cannot depend on itself.");
      else if (!keys.includes(d)) add(t.key, `It depends on "${d}", which is not in the plan.`);
    }
  }
  const cycle = findCycle(tasks);
  if (cycle) general.push(`These tasks depend on each other in a circle: ${cycle.join(" → ")}.`);
  return { general, byTask };
}

export const hasErrors = (e: PlanErrors) => e.general.length > 0 || Object.keys(e.byTask).length > 0;

export function toPlanEdit(tasks: EditTask[], criteria?: string[]): PlanEdit {
  return {
    tasks: tasks.map((t) => ({
      key: t.key,
      title: t.title.trim(),
      description: t.description.trim(),
      agent: t.agent,
      depends_on: t.dependsOn,
      tools: t.tools,
      expected_outputs: t.expectedOutputs,
      review: t.review,
      optional: t.optional,
    })),
    ...(criteria && criteria.length ? { completion_criteria: criteria } : {}),
  };
}
