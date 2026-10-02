import type { TaskNode } from "@nexus/schemas";
import { describe, expect, it } from "vitest";
import { agentName, layoutTasks, messageText, needsOf, planOf, progress, resultOf, strategyOf } from "./format";
import { blankTask, findCycle, fromPlan, hasErrors, nextKey, removeTask, toPlanEdit, validatePlan, type EditTask } from "./planEdit";

const task = (over: Partial<TaskNode>): TaskNode => ({
  id: "task_x",
  objective_id: "obj_1",
  project_id: "proj_1",
  key: "t1",
  title: "T",
  description: "",
  kind: "work",
  assigned_agent: "writer",
  status: "WAITING",
  depends_on: [],
  inputs: {},
  outputs: null,
  attempts: 0,
  max_attempts: 2,
  approval_required: false,
  optional: false,
  review: false,
  round: 0,
  parent_task_id: null,
  run_id: null,
  error: null,
  started_at: null,
  completed_at: null,
  created_at: "2026-09-29T10:00:00Z",
  ...over,
});

describe("objective views", () => {
  it("reads a plan defensively", () => {
    const p = planOf({
      plan: {
        objective: "o",
        tasks: [{ key: "t1", title: "Research", agent: "researcher", depends_on: [], review: true, approval_required: true }],
        completion_criteria: ["done"],
        warnings: ["dropped a tool"],
        follow_up: [{}],
      },
    })!;
    expect(p.tasks[0]).toMatchObject({ key: "t1", agent: "researcher", review: true, approvalRequired: true, tools: [] });
    expect(p.criteria).toEqual(["done"]);
    expect(p.warnings).toEqual(["dropped a tool"]);
    expect(p.followUps).toBe(1);
    expect(planOf({ plan: null })).toBeNull();
    expect(planOf({ plan: { tasks: "nonsense" } })!.tasks).toEqual([]);
  });

  it("reads strategy and result", () => {
    expect(strategyOf({ strategy: { name: "single_agent", rationale: "One is enough.", estimated_tokens: 15000, agents: ["writer"] } })).toEqual({
      name: "single agent",
      rationale: "One is enough.",
      tokens: 15000,
      agents: ["writer"],
    });
    const r = resultOf({
      result: {
        verdict: "PARTIAL",
        summary: "Mostly",
        criteria: [{ criterion: "a", met: true, evidence: "e" }, { criterion: "b", met: false }],
        missing_requirements: ["b"],
        artifacts: [{ artifact_id: "art_1", name: "r.md", version: 2 }],
      },
    })!;
    expect(r.verdict).toBe("PARTIAL");
    expect(r.criteria[1]).toEqual({ criterion: "b", met: false, evidence: "" });
    expect(r.artifacts).toEqual([{ id: "art_1", name: "r.md", version: 2 }]);
    expect(resultOf({ result: { verdict: "maybe" } })!.verdict).toBeNull();
  });

  it("says what a task needs from the person", () => {
    expect(needsOf(task({ status: "BLOCKED", error: { code: "needs_input", message: "Which tone?", options: ["a"] } }))).toEqual({
      kind: "question",
      message: "Which tone?",
      options: ["a"],
    });
    expect(needsOf(task({ status: "BLOCKED", error: { code: "agent_reported_failure", message: "no data" } })).kind).toBe("decision");
    expect(needsOf(task({ status: "FAILED", error: null })).message).toMatch(/could not finish/);
    expect(needsOf(task({ status: "RUNNING" })).kind).toBeNull();
  });

  it("lays the graph out by dependency depth", () => {
    const a = task({ id: "a", key: "a" });
    const b = task({ id: "b", key: "b" });
    const c = task({ id: "c", key: "c", depends_on: ["a", "b"] });
    const d = task({ id: "d", key: "d", depends_on: ["c"] });
    const laid = layoutTasks([a, b, c, d], 100, 10);
    expect(laid.map((p) => [p.task.key, p.level, p.x, p.y])).toEqual([
      ["a", 0, 0, 0],
      ["b", 0, 0, 10],
      ["c", 1, 100, 0],
      ["d", 2, 200, 0],
    ]);
    // unknown dependencies (e.g. filtered out) are ignored rather than crashing
    expect(layoutTasks([task({ id: "x", depends_on: ["ghost"] })])[0]!.level).toBe(0);
  });

  it("summarises agent hand-offs from structured fields only", () => {
    expect(messageText({ type: "TASK_RESULT", payload: { summary: "Drafted the report" } })).toBe("Drafted the report");
    expect(messageText({ type: "REVIEW_RESULT", payload: { verdict: "revise", blocking_issues: 2, summary: "Two gaps" } })).toBe(
      "Verdict: revise (2 to fix). Two gaps",
    );
    expect(messageText({ type: "ERROR", payload: { message: "Search failed", decision: "needs a person" } })).toBe("Search failed · needs a person");
    expect(messageText({ type: "QUESTION", payload: { question: 42 } })).toBe("");
    expect(agentName("orchestrator")).toBe("NEXUS");
    expect(agentName("user")).toBe("you");
    expect(agentName("data_analyst")).toBe("data analyst");
  });

  it("counts progress without the verification step", () => {
    expect(progress([task({ status: "COMPLETED" }), task({ status: "SKIPPED" }), task({ status: "RUNNING" }), task({ kind: "verify", status: "COMPLETED" })])).toEqual({
      done: 2,
      total: 3,
    });
  });
});

const agents = new Set(["researcher", "writer", "critic", "verifier", "planner"]);
const t = (key: string, over: Partial<EditTask> = {}): EditTask => ({ ...blankTask([], "writer"), key, title: key.toUpperCase(), ...over });

describe("plan editing", () => {
  it("accepts a sound plan and converts it for the API", () => {
    const tasks = [t("t1", { agent: "researcher" }), t("t2", { dependsOn: ["t1"], review: true })];
    expect(hasErrors(validatePlan(tasks, agents))).toBe(false);
    expect(toPlanEdit(tasks, ["done"])).toEqual({
      tasks: [
        { key: "t1", title: "T1", description: "", agent: "researcher", depends_on: [], tools: [], expected_outputs: [], review: false, optional: false },
        { key: "t2", title: "T2", description: "", agent: "writer", depends_on: ["t1"], tools: [], expected_outputs: [], review: true, optional: false },
      ],
      completion_criteria: ["done"],
    });
    expect(toPlanEdit(tasks, [])).not.toHaveProperty("completion_criteria");
  });

  it("explains every problem", () => {
    const e = validatePlan(
      [t("t1", { title: " " }), t("t1"), t("bad key!"), t("t3", { agent: "wizard" }), t("t4", { agent: "verifier" }), t("t5", { dependsOn: ["t5", "zz"] })],
      agents,
    );
    expect(e.byTask["t1"]).toEqual(expect.arrayContaining(["Give the task a title.", 'The key "t1" is used twice.']));
    expect(e.byTask["bad key!"]![0]).toMatch(/letters, digits/);
    expect(e.byTask["t3"]![0]).toMatch(/not an available agent/);
    expect(e.byTask["t4"]![0]).toMatch(/fixed role/);
    expect(e.byTask["t5"]).toEqual(["A task cannot depend on itself.", 'It depends on "zz", which is not in the plan.']);
    expect(validatePlan([], agents).general[0]).toMatch(/at least one task/);
  });

  it("finds dependency cycles", () => {
    const tasks = [t("a", { dependsOn: ["c"] }), t("b", { dependsOn: ["a"] }), t("c", { dependsOn: ["b"] })];
    const cycle = findCycle(tasks)!;
    expect(new Set(cycle)).toEqual(new Set(["a", "b", "c"]));
    expect(validatePlan(tasks, agents).general[0]).toMatch(/in a circle/);
    expect(findCycle([t("a"), t("b", { dependsOn: ["a"] })])).toBeNull();
  });

  it("removing a task also removes references to it", () => {
    const tasks = removeTask([t("t1"), t("t2", { dependsOn: ["t1"] })], "t1");
    expect(tasks).toHaveLength(1);
    expect(tasks[0]!.dependsOn).toEqual([]);
  });

  it("picks fresh keys and copies plans", () => {
    expect(nextKey([t("t1"), t("t2")])).toBe("t3");
    expect(nextKey([t("t3")])).toBe("t2");
    expect(nextKey([t("t2"), t("t3")])).toBe("t4");
    const copied = fromPlan([{ key: "t1", title: "x", description: "", agent: "writer", dependsOn: ["a"], tools: [], expectedOutputs: [], approvalRequired: false, optional: false, review: false }]);
    expect(copied[0]!.dependsOn).toEqual(["a"]);
  });
});
