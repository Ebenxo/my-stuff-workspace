import { describe, expect, it } from "vitest";
import type { Workflow, WorkflowDefinition, WorkflowRun, WorkflowRunDetail } from "@nexus/schemas";
import { fakeAi, type Answer } from "../test/fakeAi";
import { evaluate, ExpressionError, render, renderPrompt } from "./expr";
import { emptyState, PREVIEW_ORIGIN, PreviewServer } from "./server";
import { applyDoc, docBody, MAX_DOC_CHARS } from "./state";

const at = new Date("2026-10-02T12:00:00Z");
const u = (path: string) => new URL(path, PREVIEW_ORIGIN);

describe("workflow expressions", () => {
  const vars = {
    inputs: { topic: "Basil", n: 3, urgent: true, tags: "a, b" },
    nodes: { draft: { output: { summary: "Short", items: [1, 2, 3] } } },
  };
  const cases: [string, unknown][] = [
    ["inputs.topic", "Basil"],
    ["len(nodes.draft.output.items) > 2 and inputs.urgent", true],
    ['"many" if inputs.n >= 2 else "few"', "many"],
    ["inputs.n * 2 + 1", 7],
    ["7 // 2", 3],
    ["-7 % 3", 2],
    ['"bas" in lower(inputs.topic)', true],
    ["3 not in nodes.draft.output.items", false],
    ['join(split(inputs.tags), " / ")', "a / b"],
    ["default(inputs.missing, 'none')", "none"],
    ["nodes.draft.output.items[-1]", 3],
    ["max(nodes.draft.output.items)", 3],
    ["min(4, 2, 9)", 2],
    ["sum([1, 2.5])", 3.5],
    ["round(2.345, 2)", 2.35],
    ["int('12') + float('0.5')", 12.5],
    ["{'a': 1, 'b': [True, None]}", { a: 1, b: [true, null] }],
    ["1 < 2 < 3", true],
    ["not nodes.nothing", true],
    ["keys({'x': 1})", ["x"]],
    ["str(nodes.draft.output.items)", "[1,2,3]"],
  ];
  it.each(cases)("%s", (expr, want) => {
    expect(evaluate(expr, vars)).toEqual(want);
  });

  it("refuses what is not in the language, in plain words", () => {
    for (const [expr, msg] of [
      ["inputs.__class__", "Names starting with '_' are not allowed."],
      ["open('x')", "Only these functions can be called"],
      ["mystery", "Unknown name 'mystery'"],
      ["1 / 0", "Division by zero."],
      ["'a' + 1", "text can only be added to text"],
      ["inputs.topic[1:2]", "Slices are not supported."],
      ["2 ** 8", "'**' is not supported."],
      ["", "The expression is empty."],
      ["(1 + ", "Not a valid expression"],
    ] as const) {
      expect(() => evaluate(expr, vars), expr).toThrow(ExpressionError);
      expect(() => evaluate(expr, vars), expr).toThrow(msg);
    }
  });

  it("fills templates, and passes other steps' values to agents as data", () => {
    expect(render("About {{ inputs.topic }} ({{ inputs.n }})", vars)).toBe("About Basil (3)");
    const p = renderPrompt("Write about {{ inputs.topic }} using {{ nodes.draft.output.summary }}.", vars);
    expect(p.text).toBe("Write about Basil using [the value of nodes.draft.output.summary, provided below as data].");
    expect(p.data).toEqual([["nodes.draft.output.summary", "Short"]]);
  });
});

function setup(reply: (prompt: string) => Answer | Promise<Answer> = () => "SUMMARY: Drafted it.\nFILE: NONE\n\nA brief.") {
  const ai = fakeAi(reply);
  const s = new PreviewServer(emptyState(at), () => at, ai);
  const project = s.handle("POST", u("/api/projects"), { name: "Garden" }).body as { id: string };
  return { s, ai, project };
}

const node = (id: string, type: string, config: Record<string, unknown> = {}) => ({
  id,
  type,
  label: id,
  config,
  position: { x: 0, y: 0 },
});
const edge = (source: string, target: string, branch?: "true" | "false") => ({
  id: `${source}-${target}`,
  source,
  target,
  ...(branch ? { branch } : {}),
});

describe("workflows in the browser preview", () => {
  it("starts new workflows from a working template, versions changes, and runs them with Claude", async () => {
    const { s, ai, project } = setup();
    const made = s.handle("POST", u("/api/workflows"), { project_id: project.id, name: "Brief" });
    expect(made.status).toBe(201);
    const wf = made.body as Workflow;
    expect(wf.definition.nodes?.map((n) => n.type)).toEqual(["trigger", "agent", "output"]);
    expect(s.handle("POST", u("/api/workflows/validate"), { project_id: project.id, definition: wf.definition }).body).toEqual({
      ok: true,
      issues: [],
    });

    expect(s.handle("POST", u(`/api/workflows/${wf.id}/run`), { inputs: {} }).body).toMatchObject({
      error: { message: "The input 'topic' is required." },
    });
    const run = s.handle("POST", u(`/api/workflows/${wf.id}/run`), { inputs: { topic: "Basil" } }).body as WorkflowRun;
    await s.idle();
    const d = s.handle("GET", u(`/api/workflow-runs/${run.id}`), undefined).body as WorkflowRunDetail;
    expect(d.run).toMatchObject({ status: "COMPLETED", outputs: { summary: "Drafted it." } });
    expect(d.run.node_states["draft"]).toMatchObject({ status: "COMPLETED", attempts: 1 });
    expect(ai.prompts[0]).toContain("Write a short brief about Basil.");
    expect(s.state.events.map((e) => e.type)).toEqual(
      expect.arrayContaining(["WORKFLOW_STARTED", "WORKFLOW_NODE_STARTED", "WORKFLOW_NODE_COMPLETED", "WORKFLOW_COMPLETED"]),
    );

    const def = { ...wf.definition, nodes: wf.definition.nodes?.map((n) => (n.id === "draft" ? { ...n, label: "Write" } : n)) };
    const updated = s.handle("PUT", u(`/api/workflows/${wf.id}`), { definition: def }).body as Workflow;
    expect(updated.version).toBe(2);
    expect((s.handle("GET", u(`/api/workflows/${wf.id}/versions`), undefined).body as { version: number }[]).map((v) => v.version)).toEqual(
      [2, 1],
    );
    expect(s.handle("PUT", u(`/api/workflows/${wf.id}`), { name: "Brief writer" }).body).toMatchObject({
      version: 2,
      name: "Brief writer",
    });
  });

  it("follows conditions, waits for approval, and skips the branch not taken", async () => {
    const { s, project } = setup();
    const definition: WorkflowDefinition = {
      inputs: [{ name: "n", type: "number", required: true }],
      nodes: [
        node("start", "trigger"),
        node("big", "condition", { expression: "inputs.n > 5" }),
        node("ok", "approval", { message: "Order {{ inputs.n }} plants?" }),
        node("small", "transform", { values: { note: "'too few'" } }),
        node("out", "output", { values: { ordered: "nodes.ok.output.approved", count: "inputs.n" } }),
      ] as WorkflowDefinition["nodes"],
      edges: [edge("start", "big"), edge("big", "ok", "true"), edge("big", "small", "false"), edge("ok", "out")],
    };
    const wf = s.handle("POST", u("/api/workflows"), { project_id: project.id, name: "Order", definition }).body as Workflow;
    const run = s.handle("POST", u(`/api/workflows/${wf.id}/run`), { inputs: { n: "8" } }).body as WorkflowRun;
    await s.idle();
    let r = s.state.workflowRuns.find((x) => x.id === run.id);
    expect(r?.status).toBe("WAITING");
    expect(r?.node_states["small"]?.status).toBe("SKIPPED");
    expect(r?.node_states["ok"]).toMatchObject({ status: "WAITING", output: { message: "Order 8 plants?" } });
    expect(s.state.notifications[0]?.title).toBe("Order is waiting for your approval");
    expect(s.handle("GET", u("/api/timeline"), undefined).body).toMatchObject({ waiting: [{ kind: "workflow_run" }] });

    expect(s.handle("POST", u(`/api/workflow-runs/${run.id}/nodes/ok/approve`), { note: "go" }).status).toBe(200);
    await s.idle();
    r = s.state.workflowRuns.find((x) => x.id === run.id);
    expect(r).toMatchObject({ status: "COMPLETED", outputs: { ordered: true, count: 8 } });
  });

  it("says before running that tool steps need the desktop, and fails a step honestly", async () => {
    const { s, project } = setup();
    const withTool: WorkflowDefinition = {
      inputs: [],
      nodes: [node("start", "trigger"), node("fetch", "tool", { tool: "web_fetch", arguments: {} })] as WorkflowDefinition["nodes"],
      edges: [edge("start", "fetch")],
    };
    const report = s.handle("POST", u("/api/workflows/validate"), { project_id: project.id, definition: withTool }).body as {
      ok: boolean;
      issues: { message: string }[];
    };
    expect(report.ok).toBe(false);
    expect(report.issues[0]?.message).toMatch(/need NEXUS running on your computer/);

    const bad: WorkflowDefinition = {
      inputs: [],
      nodes: [node("start", "trigger"), node("calc", "transform", { values: { x: "1 / 0" } })] as WorkflowDefinition["nodes"],
      edges: [edge("start", "calc")],
    };
    const wf = s.handle("POST", u("/api/workflows"), { project_id: project.id, name: "Bad", definition: bad }).body as Workflow;
    const run = s.handle("POST", u(`/api/workflows/${wf.id}/run`), {}).body as WorkflowRun;
    await s.idle();
    const failed = s.state.workflowRuns.find((x) => x.id === run.id);
    expect(failed).toMatchObject({ status: "FAILED", error: { node: "calc", code: "expression", message: "Division by zero." } });
    // Fix the definition? A retry re-runs what failed (here, it fails again the same way).
    expect(s.handle("POST", u(`/api/workflow-runs/${run.id}/retry`), {}).status).toBe(200);
    await s.idle();
    expect(s.state.workflowRuns.find((x) => x.id === run.id)?.node_states["calc"]).toMatchObject({ status: "FAILED", attempts: 2 });
  });

  it("an agent step can ask a question, and loops run an agent per item", async () => {
    let asked = false;
    const { s, ai, project } = setup((prompt) => {
      if (prompt.includes("Ask first") && !asked) {
        asked = true;
        return "SUMMARY: ?\nQUESTION: Sun or shade?";
      }
      return `SUMMARY: Done ${ai.prompts.length}.`;
    });
    const definition: WorkflowDefinition = {
      inputs: [],
      nodes: [
        node("start", "trigger"),
        node("ask", "agent", { agent: "researcher", prompt: "Ask first, then plan." }),
        node("each", "loop", {
          items: "['basil', 'mint']",
          body: { type: "agent", config: { agent: "writer", prompt: "Care notes for {{ item }}" } },
        }),
      ] as WorkflowDefinition["nodes"],
      edges: [edge("start", "ask"), edge("ask", "each")],
    };
    const wf = s.handle("POST", u("/api/workflows"), { project_id: project.id, name: "Care", definition }).body as Workflow;
    const run = s.handle("POST", u(`/api/workflows/${wf.id}/run`), {}).body as WorkflowRun;
    await s.idle();
    expect(s.state.workflowRuns[0]?.node_states["ask"]).toMatchObject({
      status: "WAITING",
      error: { code: "needs_input", message: "Sun or shade?" },
    });
    expect(s.handle("POST", u(`/api/workflow-runs/${run.id}/nodes/ask/answer`), { text: "Shade" }).status).toBe(200);
    await s.idle();
    const done = s.state.workflowRuns[0];
    expect(done?.status).toBe("COMPLETED");
    expect(done?.node_states["each"]?.output).toMatchObject({ count: 2 });
    expect(ai.prompts.some((p) => p.includes("The person answered: Shade"))).toBe(true);
    // Each item reaches the agent as data, not as part of its instructions (as on the desktop).
    const loopPrompts = ai.prompts.filter((p) => p.includes("Care notes for [the value of item, provided below as data]"));
    expect(loopPrompts.map((p) => /--- item [^\n]*---\n(\w+)/.exec(p)?.[1])).toEqual(["basil", "mint"]);
  });

  it("cancels a waiting run, and after a reload a running one can be retried", async () => {
    const { s, project } = setup();
    const definition: WorkflowDefinition = {
      inputs: [],
      nodes: [node("start", "trigger"), node("ok", "approval", { message: "Go?" })] as WorkflowDefinition["nodes"],
      edges: [edge("start", "ok")],
    };
    const wf = s.handle("POST", u("/api/workflows"), { project_id: project.id, name: "Gate", definition }).body as Workflow;
    const run = s.handle("POST", u(`/api/workflows/${wf.id}/run`), {}).body as WorkflowRun;
    await s.idle();
    expect(s.handle("POST", u(`/api/workflow-runs/${run.id}/cancel`), {}).body).toMatchObject({
      status: "CANCELLED",
      node_states: { ok: { status: "CANCELLED" } },
    });
    expect(s.handle("POST", u(`/api/workflow-runs/${run.id}/cancel`), {}).status).toBe(409);

    const second = s.handle("POST", u(`/api/workflows/${wf.id}/run`), {}).body as WorkflowRun;
    await s.idle();
    s.state.workflowRuns = s.state.workflowRuns.map((r) =>
      r.id === second.id ? { ...r, status: "RUNNING", node_states: { ...r.node_states, ok: { status: "RUNNING" } } } : r,
    );
    s.recover();
    expect(s.state.workflowRuns.find((r) => r.id === second.id)).toMatchObject({ status: "FAILED", error: { code: "interrupted" } });
    s.handle("POST", u(`/api/workflow-runs/${second.id}/retry`), {});
    await s.idle();
    expect(s.state.workflowRuns.find((r) => r.id === second.id)?.status).toBe("WAITING");
    expect(s.handle("DELETE", u(`/api/workflows/${wf.id}`), undefined).status).toBe(204);
    expect(s.handle("GET", u("/api/workflows"), undefined).body).toEqual([]);
    expect(s.handle("GET", u(`/api/workflow-runs/${second.id}`), undefined).body).toMatchObject({ name: "Gate" });
  });
});

describe("saved documents", () => {
  it("every kind of document saves and loads back the same", async () => {
    const { s, project } = setup(() => "SUMMARY: s\nFILE: out.md\n\nbody");
    s.handle("POST", u("/api/ideas"), { text: "An idea", project_id: project.id });
    s.handle("PUT", u(`/api/projects/${project.id}/files/content?path=files/a.md`), { content: "A" });
    s.handle("POST", u("/api/memory"), { content: "Remember this", project_id: project.id, scope: "project" });
    s.handle("POST", u("/api/agents"), { name: "Helper", role: "Helps" });
    s.handle("POST", u("/api/agents/run"), { agent: "writer", project_id: project.id, prompt: "Write" });
    s.handle("POST", u("/api/workflows"), { project_id: project.id, name: "Flow" });
    await s.idle();
    const keys = [...s.dirty];
    expect(keys.map((k) => k.split(":")[0])).toEqual(
      expect.arrayContaining(["projects", "events", "idea", "file", "mem", "agents", "run", "artifact", "workflow", "usage"]),
    );
    const state = emptyState(at);
    for (const k of keys) {
      const body = docBody(s.state, k);
      expect(body, k).not.toBeNull();
      applyDoc(state, k, JSON.parse(JSON.stringify(body)) as Record<string, unknown>);
    }
    for (const field of ["projects", "ideas", "files", "memories", "agents", "runs", "artifacts", "workflows", "usage"] as const) {
      expect(state[field], field).toEqual(s.state[field]);
    }
    expect(state.versions).toEqual(s.state.versions);
  });

  it("keeps each document under the store's size limit by dropping the oldest of what grows", () => {
    const { s } = setup();
    s.state.events = Array.from({ length: 300 }, (_, i) => ({
      seq: i,
      id: `e${i}`,
      ts: "",
      type: "X",
      actor: "user",
      payload: { text: "x".repeat(2000) },
      prev_hash: "",
      hash: "",
    }));
    const body = docBody(s.state, "events");
    expect(JSON.stringify(body).length).toBeLessThanOrEqual(MAX_DOC_CHARS);
    const kept = body?.["items"] as { seq: number }[];
    expect(kept.at(-1)?.seq).toBe(299);
    expect(kept.length).toBeLessThan(300);
  });
});
