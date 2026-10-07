import { describe, expect, it } from "vitest";
import type { Objective, ObjectiveDetail } from "@nexus/schemas";
import { fakeAi, roleOf, type Answer } from "../test/fakeAi";
import { AiError } from "./ai";
import { emptyState, PREVIEW_ORIGIN, PreviewServer } from "./server";
import { applyDoc, docBody } from "./state";

const at = new Date("2026-10-02T12:00:00Z");
const u = (path: string) => new URL(path, PREVIEW_ORIGIN);

const PLAN = {
  objective: "Compare three assistants and save a report.",
  assumptions: ["The notes are the sources."],
  risks: ["Notes may be incomplete."],
  completion_criteria: ["A comparison report is saved", "It covers all three"],
  tasks: [
    { key: "t1", title: "Extract facts", description: "List price and features per note.", agent: "researcher" },
    {
      key: "t2",
      title: "Write the report",
      description: "Tables and a recommendation.",
      agent: "writer",
      depends_on: ["t1"],
      review: true,
    },
  ],
};

function setup(reply: (prompt: string, n: number) => Answer | Promise<Answer>) {
  const ai = fakeAi(reply);
  const s = new PreviewServer(emptyState(at), () => at, ai);
  s.started();
  const project = s.handle("POST", u("/api/projects"), { name: "Research" }).body as { id: string };
  return { s, ai, project };
}

const detail = (s: PreviewServer, id: string) => s.handle("GET", u(`/api/objectives/${id}`), undefined).body as ObjectiveDetail;

function create(s: PreviewServer, projectId: string, extra: Record<string, unknown> = {}): Objective {
  const r = s.handle("POST", u("/api/objectives"), {
    project_id: projectId,
    text: "Research three AI coding assistants and create a comparison report.",
    ...extra,
  });
  expect(r.status).toBe(202);
  return r.body as Objective;
}

/** The normal script: plan, facts, a report, a review that asks for one fix, the fix, a pass. */
function script(critic: "approve" | "revise" = "revise") {
  let reviews = 0;
  return (prompt: string): Answer => {
    switch (roleOf(prompt)) {
      case "planner":
        return PLAN;
      case "critic":
        reviews++;
        return critic === "revise" && reviews === 1
          ? {
              verdict: "revise",
              summary: "The pricing table has no sources.",
              issues: [{ severity: "high", blocking: true, description: "Cite the notes", suggestion: "Add a source column" }],
            }
          : { verdict: "approve", summary: "Good.", issues: [] };
      case "verifier":
        return {
          verdict: "PASS",
          summary: "All criteria are met.",
          criteria: [{ criterion: "A comparison report is saved", met: true, evidence: "artifacts/report.md" }],
          missing_requirements: [],
        };
      default:
        if (prompt.includes("This task: Extract facts"))
          return "SUMMARY: Listed the facts for all three.\nFILE: NONE\n\nAlpha $10, Beta $19, Gamma $15.";
        if (prompt.includes("Revise this task's deliverable"))
          return "SUMMARY: Added sources.\nFILE: report.md\n\n# Report\n\n| Tool | Price | Source |";
        return "SUMMARY: Wrote the comparison.\nFILE: report.md\n\n# Report\n\n| Tool | Price |";
    }
  };
}

describe("objectives in the browser preview", () => {
  it("plans, waits for the person, then works, reviews, revises and verifies", async () => {
    const { s, ai, project } = setup(script());
    s.handle("PUT", u(`/api/projects/${project.id}/files/content?path=files/notes/alpha.md`), { content: "# Alpha\n$10" });
    const o = create(s, project.id);
    expect(o.status).toBe("RECEIVED");
    await s.idle();

    let d = detail(s, o.id);
    expect(d.objective.status).toBe("AWAITING_PLAN_APPROVAL");
    expect(d.objective.strategy).toMatchObject({ name: "reviewer", agents: ["researcher", "writer"] });
    expect(d.tasks.map((t) => [t.key, t.status, t.assigned_agent])).toEqual([
      ["t1", "QUEUED", "researcher"],
      ["t2", "WAITING", "writer"],
    ]);
    expect(d.tasks[1]?.depends_on).toEqual([d.tasks[0]?.id]);
    expect(ai.prompts[0]).toContain("files/notes/alpha.md");
    expect(s.state.notifications[0]?.title).toMatch(/^Plan ready/);

    expect(s.handle("POST", u(`/api/objectives/${o.id}/run`), { mode: "normal" }).status).toBe(202);
    await s.idle();
    d = detail(s, o.id);
    expect(d.objective.status).toBe("COMPLETED");
    expect(d.tasks.map((t) => [t.key, t.kind, t.status])).toEqual([
      ["t1", "work", "COMPLETED"],
      ["t2", "work", "COMPLETED"],
      ["t2-review1", "review", "COMPLETED"],
      ["t2-rev1", "revise", "COMPLETED"],
      ["verify1", "verify", "COMPLETED"],
    ]);
    // The writer saw the researcher's facts; the revision saw the Critic's notes and the first draft.
    const writer = ai.prompts.find((p) => p.includes("This task: Write the report")) ?? "";
    expect(writer).toContain("Alpha $10, Beta $19, Gamma $15.");
    expect(writer).toContain("--- files/notes/alpha.md ---");
    const revise = ai.prompts.find((p) => p.includes("Revise this task's deliverable")) ?? "";
    expect(revise).toContain("Cite the notes");
    expect(revise).toContain("--- artifacts/report.md ---");

    const report = s.state.artifacts.find((a) => a.name === "report.md");
    expect(report).toMatchObject({ version: 2, objective_id: o.id });
    expect(d.objective.result).toMatchObject({ verdict: "PASS", artifacts: [{ artifact_id: report?.id, name: "report.md", version: 2 }] });
    expect(d.messages.map((m) => m.type)).toEqual(
      expect.arrayContaining(["TASK_REQUEST", "TASK_RESULT", "REVIEW_REQUEST", "REVIEW_RESULT"]),
    );

    const types = s.state.events.map((e) => e.type);
    for (const t of [
      "OBJECTIVE_CREATED",
      "PLAN_CREATED",
      "PLAN_APPROVED",
      "TASK_STARTED",
      "AGENT_COMPLETED",
      "ARTIFACT_CREATED",
      "ARTIFACT_UPDATED",
      "REVIEW_COMPLETED",
      "VERIFICATION_COMPLETED",
      "OBJECTIVE_COMPLETED",
    ]) {
      expect(types).toContain(t);
    }
    // Runs are recorded per agent, with usage; the finished objective suggests a memory to keep.
    expect(s.state.runs.filter((r) => r.objective_id === o.id).map((r) => r.status)).toEqual(Array(6).fill("COMPLETED"));
    expect(s.state.usage.length).toBe(6);
    expect(s.state.memories).toMatchObject([{ status: "pending", source: { kind: "objective" } }]);
    expect(s.handle("GET", u("/api/timeline"), undefined).body).toMatchObject({ now: [], waiting: [] });
  });

  it("lets the person edit the plan before it runs", async () => {
    const { s, project } = setup(script("approve"));
    const o = create(s, project.id);
    await s.idle();
    const edited = s.handle("PUT", u(`/api/objectives/${o.id}/plan`), {
      tasks: [{ key: "only", title: "Just write it", description: "", agent: "nobody" }],
      completion_criteria: ["A report exists"],
    });
    expect(edited.status).toBe(200);
    const d = edited.body as ObjectiveDetail;
    expect(d.tasks.map((t) => [t.key, t.assigned_agent])).toEqual([["only", "writer"]]);
    expect(d.objective.plan).toMatchObject({ edited: true, completion_criteria: ["A report exists"] });
    expect((d.objective.plan?.["warnings"] as string[])[0]).toMatch(/not an available agent/);
    s.handle("POST", u(`/api/objectives/${o.id}/run`), {});
    await s.idle();
    expect(s.handle("PUT", u(`/api/objectives/${o.id}/plan`), { tasks: [] }).status).toBe(409);
    expect(detail(s, o.id).objective.status).toBe("COMPLETED");
  });

  it("pauses when an agent asks a question, and continues with the answer", async () => {
    let asked = false;
    const { s, ai, project } = setup((prompt) => {
      if (roleOf(prompt) === "agent" && prompt.includes("This task: Extract facts") && !asked) {
        asked = true;
        return "SUMMARY: Need the region.\nQUESTION: Which region's prices?\nOPTIONS: US | EU\n";
      }
      return script("approve")(prompt);
    });
    const o = create(s, project.id, { run_mode: "auto" });
    await s.idle();
    let d = detail(s, o.id);
    expect(d.objective.status).toBe("PAUSED");
    const blocked = d.tasks.find((t) => t.key === "t1");
    expect(blocked).toMatchObject({
      status: "BLOCKED",
      error: { code: "needs_input", message: "Which region's prices?", options: ["US", "EU"] },
    });
    expect(s.handle("GET", u("/api/timeline"), undefined).body).toMatchObject({ waiting: [{ kind: "objective", status: "PAUSED" }] });

    expect(s.handle("POST", u(`/api/tasks/${blocked?.id}/answer`), { text: "EU" }).status).toBe(202);
    await s.idle();
    d = detail(s, o.id);
    expect(d.objective.status).toBe("COMPLETED");
    expect(ai.prompts.some((p) => p.includes("The person answered: EU"))).toBe(true);
  });

  it("retries a failed task once, then waits for the person", async () => {
    const { s, project } = setup((prompt) =>
      roleOf(prompt) === "planner" ? PLAN : new AiError("unavailable", "Claude could not answer just now."),
    );
    const o = create(s, project.id, { run_mode: "auto" });
    await s.idle();
    const d = detail(s, o.id);
    expect(d.objective).toMatchObject({ status: "PAUSED", error: { message: "Claude could not answer just now." } });
    expect(d.tasks[0]).toMatchObject({ status: "FAILED", attempts: 2 });
    expect(s.state.events.filter((e) => e.type === "TASK_RETRIED")).toHaveLength(1);
    expect(s.handle("POST", u(`/api/tasks/${d.tasks[1]?.id}/skip`), {}).status).toBe(202);
  });

  it("fails honestly when Claude cannot plan", async () => {
    const { s, project } = setup(() => new AiError("not_granted", "This page was not allowed to use Claude."));
    const o = create(s, project.id);
    await s.idle();
    expect(detail(s, o.id).objective).toMatchObject({ status: "FAILED", error: { code: "not_granted" } });
  });

  it("stops when cancelled mid-task", async () => {
    let release: () => void = () => undefined;
    const { s, project } = setup((prompt) => {
      if (roleOf(prompt) === "planner") return PLAN;
      return new Promise<Answer>((resolve) => (release = () => resolve("SUMMARY: late")));
    });
    const o = create(s, project.id, { run_mode: "auto" });
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    expect(detail(s, o.id).objective.status).toBe("RUNNING");
    expect(s.handle("POST", u(`/api/objectives/${o.id}/cancel`), {}).body).toMatchObject({ status: "CANCELLED" });
    release();
    await s.idle();
    const d = detail(s, o.id);
    expect(d.objective.status).toBe("CANCELLED");
    expect(s.state.runs.every((r) => r.status !== "RUNNING")).toBe(true);
    expect(d.tasks.every((t) => t.status === "CANCELLED")).toBe(true);
  });

  it("starts an idea as an objective, and the demo with its labelled notes", async () => {
    const { s, project } = setup(script("approve"));
    const idea = s.handle("POST", u("/api/ideas"), { text: "Compare garden planners", project_id: project.id }).body as { id: string };
    const r = s.handle("POST", u(`/api/ideas/${idea.id}/objective`), {});
    expect(r.status).toBe(202);
    const { objective } = r.body as { objective: Objective };
    expect(s.state.ideas[0]?.objective_id).toBe(objective.id);
    expect(s.handle("POST", u(`/api/ideas/${idea.id}/objective`), {}).status).toBe(409);

    const demo = s.handle("POST", u("/api/demo"), {});
    expect(demo.status).toBe(202);
    const demoProject = s.state.projects.find((p) => p.is_demo);
    expect(demoProject?.name).toBe("Demo: AI coding assistants");
    const notes = s.state.files.filter((f) => f.project_id === demoProject?.id);
    expect(notes.map((f) => f.path)).toEqual(["files/notes/alpha-code.md", "files/notes/beta-pair.md", "files/notes/gamma-dev.md"]);
    expect(notes.every((f) => f.content.startsWith("> DEMO DATA"))).toBe(true);
    await s.idle();
  });

  it("after a reload, what was running waits to be resumed", async () => {
    const { s, project } = setup(script("approve"));
    const o = create(s, project.id, { run_mode: "auto" });
    await s.idle();
    // Pretend the page closed mid-run: save, reload into a fresh server, recover.
    s.state.objectives = s.state.objectives.map((x) => (x.id === o.id ? { ...x, status: "RUNNING" } : x));
    const docs = new Map<string, Record<string, unknown>>();
    for (const key of ["projects", "events", `objective:${o.id}`]) docs.set(key, docBody(s.state, key) ?? {});
    const state = emptyState(at);
    for (const [k, b] of docs) applyDoc(state, k, b);
    const again = new PreviewServer(state, () => at, fakeAi(script("approve")));
    again.recover();
    expect(detail(again, o.id).objective).toMatchObject({ status: "PAUSED", error: { code: "interrupted" } });
    expect(again.handle("POST", u(`/api/objectives/${o.id}/resume`), {}).status).toBe(202);
    await again.idle();
    expect(detail(again, o.id).objective.status).toBe("COMPLETED");
  });
});
