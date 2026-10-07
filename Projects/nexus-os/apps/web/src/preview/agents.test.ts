import { describe, expect, it } from "vitest";
import type { Agent, AgentRun, MemoryHit, MemoryItem, RunDetail } from "@nexus/schemas";
import { fakeAi, type Answer } from "../test/fakeAi";
import { parseReply } from "./agents";
import { emptyState, PREVIEW_ORIGIN, PreviewServer } from "./server";

const at = new Date("2026-10-02T12:00:00Z");
const u = (path: string) => new URL(path, PREVIEW_ORIGIN);

function setup(reply: (prompt: string) => Answer | Promise<Answer> = () => "SUMMARY: ok") {
  const ai = fakeAi(reply);
  const s = new PreviewServer(emptyState(at), () => at, ai);
  const project = s.handle("POST", u("/api/projects"), { name: "Kitchen" }).body as { id: string };
  return { s, ai, project };
}

describe("agent runs", () => {
  it("reads the reply format, forgivingly", () => {
    expect(parseReply("SUMMARY: Did it.\nFILE: plan.md\n\n# Plan\nbody")).toEqual({
      summary: "Did it.",
      file: "plan.md",
      question: null,
      options: [],
      body: "# Plan\nbody",
    });
    expect(parseReply("**Summary:** Short\nFile: NONE\n\nJust an answer")).toMatchObject({
      summary: "Short",
      file: null,
      body: "Just an answer",
    });
    expect(parseReply("No header at all\nsecond line")).toMatchObject({
      summary: "No header at all",
      file: null,
      body: "No header at all\nsecond line",
    });
    expect(parseReply("SUMMARY: ?\nQUESTION: Which oven?\nOPTIONS: Gas | Electric\n")).toMatchObject({
      question: "Which oven?",
      options: ["Gas", "Electric"],
    });
  });

  it("runs an agent with Claude, saves its deliverable and records every step", async () => {
    const { s, ai, project } = setup(() => "SUMMARY: Wrote a menu.\nFILE: menu plan.md\n\n# Menu\n- Soup");
    s.handle("PUT", u(`/api/projects/${project.id}/files/content?path=files/pantry.md`), { content: "lentils, rice" });
    s.handle("POST", u("/api/memory"), { content: "The person is vegetarian.", project_id: project.id, scope: "project" });
    const r = s.handle("POST", u("/api/agents/run"), {
      agent: "writer",
      project_id: project.id,
      prompt: "Plan dinners for the week",
      model: "prov_claude:quick",
    });
    expect(r.status).toBe(202);
    const started = r.body as AgentRun;
    expect(started).toMatchObject({ status: "RUNNING", model: "prov_claude:quick" });
    await s.idle();

    const d = s.handle("GET", u(`/api/runs/${started.id}`), undefined).body as RunDetail;
    expect(d.run).toMatchObject({
      status: "COMPLETED",
      result: { summary: "Wrote a menu.", artifacts: [{ name: "menu-plan.md", version: 1 }] },
    });
    expect(d.steps.map((x) => (x["action"] as { type: string; tool?: string }).tool ?? (x["action"] as { type: string }).type)).toEqual([
      "read_file",
      "create_markdown",
      "finish",
    ]);
    expect(ai.prompts[0]).toContain("lentils, rice");
    expect(ai.prompts[0]).toContain("The person is vegetarian.");
    expect(ai.prompts[0]).toContain("you have no tools");

    const content = s.handle("GET", u(`/api/projects/${project.id}/files/content?path=artifacts/menu-plan.md`), undefined).body;
    expect(content).toMatchObject({ content: "# Menu\n- Soup" });
    const runs = s.handle("GET", u(`/api/runs?project_id=${project.id}&agent=writer`), undefined).body as AgentRun[];
    expect(runs.map((x) => x.id)).toEqual([started.id]);
    const usage = s.handle("GET", u("/api/usage/summary?days=7&group_by=agent"), undefined).body as {
      total_calls: number;
      groups: { key: string }[];
    };
    expect(usage).toMatchObject({ total_calls: 1, groups: [{ key: "writer" }] });
  });

  it("asks the person when it must, and continues with the answer", async () => {
    let n = 0;
    const { s, ai, project } = setup(() =>
      ++n === 1 ? "SUMMARY: ?\nQUESTION: How many people?\nOPTIONS: 2 | 4" : "SUMMARY: Done for four.\nFILE: NONE\n\nFour portions.",
    );
    const run = s.handle("POST", u("/api/agents/run"), { agent: "writer", project_id: project.id, prompt: "Plan" }).body as AgentRun;
    await s.idle();
    let d = s.handle("GET", u(`/api/runs/${run.id}`), undefined).body as RunDetail;
    expect(d.run).toMatchObject({ status: "WAITING_INPUT", result: { question: "How many people?", options: ["2", "4"] } });
    expect(s.handle("GET", u("/api/timeline"), undefined).body).toMatchObject({ waiting: [{ kind: "agent_run" }] });
    expect(s.handle("POST", u(`/api/runs/${run.id}/answer`), { text: "4" }).status).toBe(202);
    await s.idle();
    d = s.handle("GET", u(`/api/runs/${run.id}`), undefined).body as RunDetail;
    expect(d.run).toMatchObject({ status: "COMPLETED", result: { answer: "Four portions." } });
    expect(ai.prompts[1]).toContain("The person answered: 4");
  });

  it("can be cancelled, and after a reload a running one can be resumed", async () => {
    let release: (a: Answer) => void = () => undefined;
    const { s, project } = setup(() => new Promise<Answer>((r) => (release = r)));
    const run = s.handle("POST", u("/api/agents/run"), { agent: "researcher", project_id: project.id, prompt: "Look into it" })
      .body as AgentRun;
    await new Promise((r) => setTimeout(r, 0));
    expect(s.handle("POST", u(`/api/runs/${run.id}/cancel`), {}).body).toMatchObject({ status: "CANCELLED" });
    release("SUMMARY: too late");
    await s.idle();
    expect(s.state.runs[0]?.status).toBe("CANCELLED");

    s.state.runs = s.state.runs.map((r) => ({ ...r, status: "RUNNING" }));
    s.recover();
    expect(s.state.runs[0]?.status).toBe("INTERRUPTED");
    s.ai.text = async () => "SUMMARY: Picked up again.";
    expect(s.handle("POST", u(`/api/runs/${run.id}/resume`), {}).status).toBe(202);
    await s.idle();
    expect(s.state.runs[0]).toMatchObject({ status: "COMPLETED", attempt: 2 });
  });

  it("keeps the person's own agents; built-in ones can only be switched off", () => {
    const { s, project } = setup();
    const made = s.handle("POST", u("/api/agents"), { name: "Recipe tester", role: "Checks recipes", system_prompt: "Be exact." });
    expect(made.status).toBe(201);
    const mine = made.body as Agent;
    expect(mine).toMatchObject({ slug: "recipe_tester", builtin: false });
    expect(s.handle("PATCH", u(`/api/agents/${mine.id}`), { role: "Tests recipes" }).body).toMatchObject({ role: "Tests recipes" });
    expect(s.handle("PATCH", u("/api/agents/agent_builtin_writer"), { system_prompt: "x" }).status).toBe(403);
    expect(s.handle("PATCH", u("/api/agents/agent_builtin_writer"), { status: "disabled" }).body).toMatchObject({ status: "disabled" });
    const writer = (s.handle("GET", u("/api/agents"), undefined).body as Agent[]).find((a) => a.slug === "writer");
    expect(writer?.status).toBe("disabled");
    expect(s.handle("POST", u("/api/agents/run"), { agent: "writer", project_id: project.id, prompt: "x" }).status).toBe(409);
    expect(s.handle("DELETE", u("/api/agents/agent_builtin_writer"), undefined).status).toBe(403);
    expect(s.handle("DELETE", u(`/api/agents/${mine.id}`), undefined).status).toBe(204);
    expect((s.handle("GET", u("/api/agents"), undefined).body as Agent[]).length).toBe(10);
  });
});

describe("project files and deliverables", () => {
  it("lists, writes, reads and deletes the person's files; deliverables are read-only with versions", async () => {
    const { s, project } = setup(() => "SUMMARY: v\nFILE: notes.md\n\nbody");
    const base = `/api/projects/${project.id}/files`;
    expect(s.handle("GET", u(base), undefined).body).toEqual([{ path: "files", kind: "dir", size: 0, modified: 0 }]);
    expect(s.handle("PUT", u(`${base}/content?path=files/a/b.md`), { content: "hello" }).status).toBe(200);
    expect(s.handle("PUT", u(`${base}/content?path=../escape.md`), { content: "x" }).status).toBe(422);
    expect(s.handle("PUT", u(`${base}/content?path=artifacts/x.md`), { content: "x" }).status).toBe(403);
    expect(s.handle("GET", u(`${base}?path=files`), undefined).body).toMatchObject([{ path: "files/a", kind: "dir" }]);
    expect(s.handle("GET", u(`${base}?path=files/a`), undefined).body).toMatchObject([{ path: "files/a/b.md", kind: "file", size: 5 }]);
    expect(s.state.events.at(-1)).toMatchObject({ type: "FILE_WRITTEN", payload: { path: "files/a/b.md", created: true } });

    for (let i = 0; i < 2; i++) {
      s.handle("POST", u("/api/agents/run"), { agent: "writer", project_id: project.id, prompt: "Write notes" });
      await s.idle();
    }
    const [artifact] = s.handle("GET", u(`/api/projects/${project.id}/artifacts`), undefined).body as { id: string; version: number }[];
    expect(artifact?.version).toBe(2);
    const versions = s.handle("GET", u(`/api/artifacts/${artifact?.id}/versions`), undefined).body as { version: number }[];
    expect(versions.map((v) => v.version)).toEqual([2, 1]);
    expect(s.handle("GET", u(`/api/artifacts/${artifact?.id}/content?version=1`), undefined).body).toMatchObject({
      content: "body",
      version: 1,
    });
    expect(s.handle("GET", u(base), undefined).body).toMatchObject([{ path: "files" }, { path: "artifacts" }]);
    const hits = (s.handle("GET", u("/api/search?q=body&kinds=artifact"), undefined).body as { hits: { kind: string }[] }).hits;
    expect(hits).toMatchObject([{ kind: "artifact" }]);

    expect(s.handle("DELETE", u(`${base}?path=files/a`), undefined).status).toBe(200);
    expect(s.handle("GET", u(`${base}/content?path=files/a/b.md`), undefined).status).toBe(404);
    expect(s.handle("DELETE", u(`${base}?path=artifacts/notes.md`), undefined).status).toBe(403);
  });
});

describe("memory", () => {
  it("remembers, refuses secrets, ranks search with a visible score, and keeps suggestions pending", () => {
    const { s, project } = setup();
    const add = (content: string, extra: Record<string, unknown> = {}) =>
      s.handle("POST", u("/api/memory"), { content, project_id: project.id, scope: "project", ...extra });
    const oven = add("The oven runs hot; bake 10 degrees lower.", { tags: ["Oven"] });
    expect(oven.status).toBe(201);
    expect(oven.body).toMatchObject({ importance: 0.8, tags: ["oven"], source: { kind: "user" }, status: "active" });
    add("Buy flour at the market on Saturdays.");
    add("Pinned: no peanuts in anything.", { pinned: true });
    expect(add("api_key = sk-ant-abcdefghijklmnopqrstuvwx1234").status).toBe(422);
    expect(add("Card 4111 1111 1111 1111 for the shop").body).toMatchObject({ error: { code: "sensitive_data" } });
    expect(s.state.events.filter((e) => e.type === "MEMORY_REJECTED")).toHaveLength(2);

    const hits = s.handle("GET", u(`/api/memory/search?q=oven+bake&project_id=${project.id}`), undefined).body as MemoryHit[];
    expect(hits.map((h) => h.item.content)).toEqual(["The oven runs hot; bake 10 degrees lower."]);
    expect(hits[0]?.score).toMatchObject({ keyword: 1, importance: 0.8, task: 0.5 });
    expect(hits[0]?.score.total).toBeGreaterThan(0.5);

    const stats = () => s.handle("GET", u(`/api/memory/stats?project_id=${project.id}`), undefined).body;
    expect(stats()).toEqual({ active: 3, pending: 0, deleted: 0 });
    const item = oven.body as MemoryItem;
    expect(s.handle("PATCH", u(`/api/memory/${item.id}`), { pinned: true }).body).toMatchObject({ importance: 1 });
    expect(s.handle("DELETE", u(`/api/memory/${item.id}`), undefined).status).toBe(204);
    expect(stats()).toEqual({ active: 2, pending: 0, deleted: 1 });
    expect(s.handle("POST", u(`/api/memory/${item.id}/restore`), {}).body).toMatchObject({ status: "active" });
    expect(s.handle("DELETE", u(`/api/memory/${item.id}?purge=true`), undefined).status).toBe(204);
    expect(s.handle("GET", u(`/api/memory/${item.id}`), undefined).status).toBe(404);
  });

  it("folds old, low-value notes that belong together into one summary, and can undo it", () => {
    const { s, project } = setup();
    for (const text of ["Tomatoes need staking in June.", "Tomatoes split after heavy rain.", "Tomatoes ripen faster on the south bed."]) {
      s.handle("POST", u("/api/memory"), { content: text, project_id: project.id, scope: "project", tags: ["tomatoes"] });
    }
    // Make them old, agent-written notes (only those are folded).
    s.state.memories = s.state.memories.map((m) => ({
      ...m,
      importance: 0.5,
      source: { kind: "agent" },
      updated_at: "2026-01-01T00:00:00Z",
    }));
    const report = s.handle("POST", u("/api/memory/compress"), { project_id: project.id, older_than_days: 30 }).body as {
      compressed: number;
      summaries: string[];
    };
    expect(report).toMatchObject({ compressed: 3, groups: 1 });
    const summary = s.state.memories.find((m) => m.id === report.summaries[0]);
    expect(summary?.content).toContain("Tomatoes need staking in June.");
    expect(s.state.memories.filter((m) => m.status === "deleted" && m.merged_into === summary?.id)).toHaveLength(3);
    const back = s.handle("POST", u(`/api/memory/${summary?.id}/undo-compression`), {}).body as MemoryItem[];
    expect(back).toHaveLength(3);
    expect(back.every((m) => m.status === "active")).toBe(true);
  });

  it("lets the person confirm or dismiss what agents suggest", async () => {
    const { s, project } = setup();
    s.handle("POST", u("/api/memory"), { content: "Keep me", project_id: project.id, scope: "project" });
    s.state.memories = s.state.memories.map((m) => ({ ...m, status: "pending" }));
    const id = s.state.memories[0]?.id ?? "";
    expect(s.handle("GET", u("/api/memory?status_filter=pending"), undefined).body).toHaveLength(1);
    expect(s.handle("POST", u(`/api/memory/${id}/confirm`), {}).body).toMatchObject({ status: "active" });
    expect(s.handle("POST", u(`/api/memory/${id}/dismiss`), {}).status).toBe(409);
  });
});
