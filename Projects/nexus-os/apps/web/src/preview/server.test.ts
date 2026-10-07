import { describe, expect, it } from "vitest";
import { emptyState, NEEDS_DESKTOP, PREVIEW_ORIGIN, PreviewServer } from "./server";
import { fakeAi } from "../test/fakeAi";

const at = new Date("2026-10-02T12:00:00Z");
const u = (path: string) => new URL(path, PREVIEW_ORIGIN);

function server(now = at) {
  const s = new PreviewServer(emptyState(now), () => now);
  s.started();
  return s;
}

function add(s: PreviewServer, body: Record<string, unknown>) {
  const r = s.handle("POST", u("/api/ideas"), body);
  expect(r.status).toBe(201);
  return r.body as { id: string; status: string; due_at: string | null; reminded_at: string | null };
}

describe("browser preview API", () => {
  it("keeps ideas, notes and to-dos, validated like the real API", () => {
    const s = server();
    const idea = add(s, { text: "  Try a darker sidebar  " });
    expect(idea).toMatchObject({ status: "open", due_at: null });
    expect(s.handle("POST", u("/api/ideas"), { text: "  " }).status).toBe(422);
    expect(s.handle("POST", u("/api/ideas"), { text: "x", kind: "task" }).status).toBe(422);
    expect(s.handle("POST", u("/api/ideas"), { text: "x", due_at: "2026-10-03T09:00:00" }).status).toBe(422);
    expect(s.handle("POST", u("/api/ideas"), { text: "x", project_id: "proj_nope" }).status).toBe(404);

    const soon = add(s, { text: "Water the basil", kind: "todo", due_at: "2026-10-03T09:00:00Z" });
    const pinned = add(s, { text: "Mulch keeps roots cool", kind: "note", pinned: true });
    const ids = (q = "") => (s.handle("GET", u(`/api/ideas${q}`), undefined).body as { id: string }[]).map((i) => i.id);
    expect(ids()).toEqual([pinned.id, soon.id, idea.id]);
    expect(ids("?kind=todo")).toEqual([soon.id]);
    expect(ids("?q=DARKER")).toEqual([idea.id]);

    const done = s.handle("PATCH", u(`/api/ideas/${soon.id}`), { status: "done" }).body as { done_at: string | null };
    expect(done.done_at).toBe(at.toISOString());
    expect(ids()).toEqual([pinned.id, idea.id]);
    expect(ids("?status_filter=all")).toHaveLength(3);
    expect(s.handle("DELETE", u(`/api/ideas/${idea.id}`), undefined).status).toBe(204);
    expect(s.handle("GET", u(`/api/ideas/${idea.id}`), undefined).status).toBe(404);
    expect([...s.dirty]).toEqual(expect.arrayContaining([`idea:${idea.id}`, `idea:${soon.id}`, "events"]));

    const types = s.state.events.map((e) => e.type);
    expect(types).toEqual(["SYSTEM_STARTED", "IDEA_CREATED", "IDEA_CREATED", "IDEA_CREATED", "IDEA_UPDATED", "IDEA_DELETED"]);
    expect(s.state.events[4]?.payload).toMatchObject({ changed: ["done_at", "status"], status: "done" });
  });

  it("builds the timeline from what is due, overdue and pinned", () => {
    const s = server();
    const overdue = add(s, { text: "Pay the water bill", kind: "todo", due_at: "2026-10-02T10:00:00Z" });
    const later = add(s, { text: "Seed swap", kind: "todo", due_at: "2026-10-04T10:00:00Z" });
    const keep = add(s, { text: "Mulch keeps roots cool", kind: "note", pinned: true });
    add(s, { text: "Just a thought" });
    const t = s.handle("GET", u("/api/timeline"), undefined).body as Record<string, { id: string; status: string }[]>;
    expect(t["waiting"]?.map((i) => [i.id, i.status])).toEqual([[overdue.id, "OVERDUE"]]);
    expect(t["next"]?.map((i) => i.id)).toEqual([later.id]);
    expect(t["pinned"]?.map((i) => i.id)).toEqual([keep.id]);
    expect(t["now"]).toEqual([]);
  });

  it("sends exactly one reminder per due time", () => {
    const s = server();
    const due = add(s, { text: "Call the nursery", kind: "todo", due_at: "2026-10-02T11:55:00Z" });
    add(s, { text: "Not yet", kind: "todo", due_at: "2026-10-05T09:00:00Z" });
    expect(s.remindDue()).toEqual([due.id]);
    expect(s.remindDue()).toEqual([]);
    const unread = s.handle("GET", u("/api/notifications/unread-count"), undefined).body;
    expect(unread).toEqual({ count: 1 });
    expect(s.state.notifications[0]?.title).toBe("To-do due: Call the nursery");
    expect(s.state.events.at(-1)).toMatchObject({ type: "IDEA_DUE", actor: "scheduler" });
    s.handle("PATCH", u(`/api/ideas/${due.id}`), { due_at: "2026-10-02T11:59:00Z" });
    expect(s.remindDue()).toEqual([due.id]); // a new due time gets its own reminder
  });

  it("pages back through history and leaves out what it is asked to", () => {
    const s = server();
    for (let n = 0; n < 5; n++) add(s, { text: `Idea ${n}` });
    const page = (q: string) => s.handle("GET", u(`/api/events?${q}`), undefined).body as { seq: number; type: string }[];
    const newest = page("newest_first=true&limit=3");
    expect(newest.map((e) => e.seq)).toEqual([6, 5, 4]);
    expect(page("newest_first=true&limit=3&before_seq=4").map((e) => e.seq)).toEqual([3, 2, 1]);
    expect(page("exclude_types=IDEA_CREATED").map((e) => e.type)).toEqual(["SYSTEM_STARTED"]);
    const live: number[] = [];
    s.onEvent((e) => live.push(e.seq));
    add(s, { text: "One more" });
    expect(live).toEqual([7]);
    expect(s.eventsAfter(6).map((e) => e.seq)).toEqual([7]);
  });

  it("keeps projects and settings, and finds ideas in search", () => {
    const s = server();
    const project = s.handle("POST", u("/api/projects"), { name: "Studio website" }).body as { id: string; slug: string };
    expect(project.slug).toBe("studio-website");
    add(s, { text: "Case-study page per project", project_id: project.id });
    expect(s.handle("PATCH", u("/api/settings"), { display_name: "Eben" }).body).toMatchObject({ display_name: "Eben" });
    const hits = (s.handle("GET", u("/api/search?q=case"), undefined).body as { hits: { kind: string }[] }).hits;
    expect(hits.map((h) => h.kind)).toEqual(["idea"]);
    const scoped = s.handle("GET", u(`/api/timeline?project_id=${project.id}`), undefined);
    expect(scoped.status).toBe(200);
  });

  it("says plainly what needs NEXUS on the computer", () => {
    const s = server();
    for (const [method, path] of [
      ["POST", "/api/mcp/servers"],
      ["POST", "/api/approvals/apr_1/decision"],
      ["PATCH", "/api/tools/read_file"],
      ["POST", "/api/providers"],
    ] as const) {
      const r = s.handle(method, u(path), {});
      expect(r.status).toBe(501);
      expect(r.body).toEqual({ error: { code: "needs_desktop", message: NEEDS_DESKTOP } });
    }
    expect(s.handle("POST", u("/api/schedules"), {}).status).toBe(501);
    expect(s.handle("GET", u("/api/approvals"), undefined)).toEqual({ status: 200, body: [] });
  });

  it("works without a model, and says so when work needs one", () => {
    const s = server();
    const project = s.handle("POST", u("/api/projects"), { name: "Garden" }).body as { id: string };
    expect((s.handle("GET", u("/api/agents"), undefined).body as unknown[]).length).toBe(10);
    expect(s.handle("GET", u("/api/providers"), undefined).body).toEqual([]);
    const r = s.handle("POST", u("/api/objectives"), { project_id: project.id, text: "Plan the beds" });
    expect(r).toMatchObject({ status: 503, body: { error: { code: "no_model" } } });
    expect(s.handle("POST", u("/api/demo"), {}).status).toBe(503);
    const health = s.handle("GET", u("/api/health"), undefined).body as { checks: { detail: string }[] };
    expect(health.checks[0]?.detail).toMatch(/No model/);
  });

  it("offers Claude as the model when the page can use it", () => {
    const s = new PreviewServer(
      emptyState(at),
      () => at,
      fakeAi(() => "SUMMARY: hi"),
    );
    const providers = s.handle("GET", u("/api/providers"), undefined).body as { name: string; kind: string }[];
    expect(providers).toMatchObject([{ kind: "anthropic", name: "Claude (your claude.ai account)" }]);
    const models = s.handle("GET", u("/api/models"), undefined).body as { ref: string; tier: string }[];
    expect(models.map((m) => [m.ref, m.tier])).toEqual([
      ["prov_claude:quick", "fast"],
      ["prov_claude:default", "balanced"],
      ["prov_claude:complex", "strong"],
    ]);
    expect(s.handle("POST", u("/api/providers/prov_claude/test"), {}).body).toMatchObject({ ok: true });
    expect(s.handle("DELETE", u("/api/providers/prov_claude"), undefined).status).toBe(403);
  });
});
