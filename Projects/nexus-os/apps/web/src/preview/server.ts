/**
 * The browser preview's stand-in for the NEXUS API.
 *
 * The preview build (`python scripts/build_preview.py`) runs the real web app with no Python API
 * behind it. Requests are answered here, in the page. Claude (through claude.ai, see `ai.ts`) is the
 * model: it plans objectives and does the agents' work. Ideas, the timeline, projects, files,
 * deliverables, memory, agents, objectives and workflows work and are saved (see `persist.ts`).
 * What only the desktop app can do (tools that touch the computer or the internet, MCP servers,
 * other model providers) answers with a plain explanation.
 *
 * No `window` here: `install.ts` wires this to `fetch`, storage and timers.
 */
import type { EventRecord, Idea, IdeaKind, Notification, Project, TimelineItem } from "@nexus/schemas";
import { claudeAi, type Ai } from "./ai";
import * as agents from "./agents";
import * as files from "./files";
import * as memory from "./memory";
import * as objectives from "./objectives";
import { MAX_EVENTS, type PreviewState } from "./state";
import * as workflows from "./workflows";

export { emptyState } from "./state";
export type { PreviewState } from "./state";

export const PREVIEW_ORIGIN = "https://nexus.preview";
const MAX_NOTIFICATIONS = 100;
const KIND_LABEL: Record<IdeaKind, string> = { idea: "Idea", note: "Note", todo: "To-do" };

export const NEEDS_DESKTOP =
  "This needs NEXUS running on your computer: the browser preview cannot reach your files, the internet, other AI providers or MCP servers. Everything else works here.";

export interface Reply {
  status: number;
  body?: unknown;
}

export type Json = Record<string, unknown>;

export interface RouteContext {
  method: string;
  path: string;
  seg: string[]; // ["api", ...]
  q: URLSearchParams;
  body: Json;
}

export const ok = (body: unknown, status = 200): Reply => ({ status, body });
export const fail = (status: number, code: string, message: string): Reply => ({ status, body: { error: { code, message } } });
export const notFound = (what: string): Reply => fail(404, "not_found", `That ${what} does not exist.`);
export const needsDesktop = (): Reply => fail(501, "needs_desktop", NEEDS_DESKTOP);

/** GET endpoints that list things the preview does not have; they are empty rather than unavailable. */
const EMPTY_LISTS = new Set(["/api/approvals", "/api/approvals/grants", "/api/mcp/servers", "/api/tool-calls"]);

export function firstLine(text: string, max = 120): string {
  return (text.trim().split("\n")[0] ?? "").slice(0, max) || "Untitled";
}

function slugify(name: string): string {
  return (
    name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 60) || "project"
  );
}

type Route = (srv: PreviewServer, ctx: RouteContext) => Reply | undefined;
const MODULE_ROUTES: Route[] = [files.route, agents.route, objectives.route, memory.route, workflows.route];

export class PreviewServer {
  readonly dirty = new Set<string>();
  private listeners = new Set<(e: EventRecord) => void>();
  private changeListeners = new Set<() => void>();
  private jobs = new Set<Promise<void>>();
  private changeScheduled = false;
  private counter = 0;

  constructor(
    public state: PreviewState,
    private clock: () => Date = () => new Date(),
    readonly ai: Ai = claudeAi(null),
  ) {}

  // ---- infrastructure --------------------------------------------------------------------------
  now(): Date {
    return this.clock();
  }

  iso(): string {
    return this.clock().toISOString();
  }

  id(prefix: string): string {
    this.counter += 1;
    return `${prefix}_${Date.now().toString(36)}${this.counter.toString(36)}${Math.random().toString(36).slice(2, 7)}`;
  }

  /** Something changed that must be saved; storage is told soon after. */
  mark(key: string): void {
    this.dirty.add(key);
    if (this.changeScheduled || this.changeListeners.size === 0) return;
    this.changeScheduled = true;
    setTimeout(() => {
      this.changeScheduled = false;
      for (const fn of this.changeListeners) fn();
    }, 0);
  }

  onChange(fn: () => void): () => void {
    this.changeListeners.add(fn);
    return () => this.changeListeners.delete(fn);
  }

  onEvent(fn: (e: EventRecord) => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  /** Background work (an objective, an agent run, a workflow). Failures are logged, never thrown. */
  spawn(work: () => Promise<void>): void {
    const job = work().catch((error: unknown) => console.error("NEXUS preview: background work failed", error));
    this.jobs.add(job);
    void job.finally(() => this.jobs.delete(job));
  }

  /** Wait until no background work is left (tests). */
  async idle(): Promise<void> {
    while (this.jobs.size) await Promise.all([...this.jobs]);
  }

  /** Events after ``seq``, oldest first (for a stream that resumes). */
  eventsAfter(seq: number): EventRecord[] {
    return this.state.events.filter((e) => e.seq > seq);
  }

  record(e: {
    type: string;
    project_id?: string | null;
    objective_id?: string | null;
    task_id?: string | null;
    run_id?: string | null;
    agent_id?: string | null;
    actor?: string;
    payload: Json;
  }): EventRecord {
    const seq = this.state.seq + 1;
    this.state.seq = seq;
    const event: EventRecord = {
      seq,
      id: `evt_${seq}`,
      ts: this.iso(),
      type: e.type,
      project_id: e.project_id ?? null,
      objective_id: e.objective_id ?? null,
      task_id: e.task_id ?? null,
      run_id: e.run_id ?? null,
      agent_id: e.agent_id ?? null,
      actor: e.actor ?? "user",
      payload: e.payload,
      prev_hash: "",
      hash: "",
    };
    this.state.events = [...this.state.events, event].slice(-MAX_EVENTS);
    this.mark("events");
    for (const fn of this.listeners) fn(event);
    return event;
  }

  notify(kind: string, title: string, projectId: string | null, ref: Json): void {
    const n: Notification = {
      id: this.id("ntf"),
      kind,
      title: title.slice(0, 200),
      body: "",
      project_id: projectId,
      ref,
      read_at: null,
      created_at: this.iso(),
    };
    this.state.notifications = [n, ...this.state.notifications].slice(0, MAX_NOTIFICATIONS);
    this.mark("notifications");
    this.record({ type: "NOTIFICATION_CREATED", project_id: projectId, payload: { notification_id: n.id, kind, title: n.title } });
  }

  project(id: string | null | undefined): Project | undefined {
    return this.state.projects.find((p) => p.id === id);
  }

  /** The first entry in a fresh preview's history. */
  started(): void {
    this.record({ type: "SYSTEM_STARTED", actor: "system", payload: { version: "0.1.0, browser preview" } });
  }

  /** After a reload: anything that was running when the page closed waits to be resumed. */
  recover(): void {
    objectives.recover(this);
    agents.recover(this);
    workflows.recover(this);
  }

  // ---- routing ---------------------------------------------------------------------------------
  handle(method: string, url: URL, body: unknown): Reply {
    const path = url.pathname.replace(/\/+$/, "") || "/";
    const q = url.searchParams;
    const m = method.toUpperCase();
    const seg = path.split("/").filter(Boolean);
    const ctx: RouteContext = { method: m, path, seg, q, body: (body ?? {}) as Json };

    if (m === "GET" && EMPTY_LISTS.has(path)) return ok([]);
    const core = this.coreRoute(ctx);
    if (core) return core;
    for (const route of MODULE_ROUTES) {
      const reply = route(this, ctx);
      if (reply) return reply;
    }
    return needsDesktop();
  }

  private coreRoute({ method: m, path, seg, q, body }: RouteContext): Reply | undefined {
    switch (`${m} ${path}`) {
      case "GET /api/health/ping":
        return ok({ ok: true });
      case "GET /api/health":
        return ok({
          status: "ok",
          version: "browser preview",
          checks: [
            {
              name: "preview",
              label: "Browser preview",
              status: "ok",
              detail: this.ai.available
                ? "Running in your browser, with Claude as the model."
                : "Running in your browser. No model is available in this view.",
              data: {},
            },
          ],
        });
      case "GET /api/settings":
        return ok(this.state.settings);
      case "PATCH /api/settings":
        return this.updateSettings(body);
      case "GET /api/projects":
        return ok(this.state.projects.filter((p) => !q.get("status_filter") || p.status === q.get("status_filter")));
      case "POST /api/projects":
        return this.createProject(body);
      case "GET /api/notifications":
        return ok(this.state.notifications.filter((n) => q.get("unread_only") !== "true" || !n.read_at));
      case "GET /api/notifications/unread-count":
        return ok({ count: this.state.notifications.filter((n) => !n.read_at).length });
      case "POST /api/notifications/read-all":
        return this.readAll();
      case "GET /api/events":
        return ok(this.queryEvents(q));
      case "GET /api/events/verify":
        return ok({
          ok: true,
          chains_checked: 1,
          events_checked: this.state.events.length,
          first_bad_seq: null,
          detail: "The browser preview keeps a plain history, without the hash chain.",
        });
      case "GET /api/search":
        return ok(this.search(q.get("q") ?? "", q.getAll("kinds")));
      case "GET /api/ideas":
        return ok(this.listIdeas(q));
      case "POST /api/ideas":
        return this.createIdea(body);
      case "GET /api/ideas/due-count":
        return ok({ count: this.state.ideas.filter((i) => i.status === "open" && i.due_at && new Date(i.due_at) <= this.now()).length });
      case "GET /api/timeline":
        return ok(this.timeline(q.get("project_id")));
    }
    if (seg[1] === "projects" && seg[2]) {
      const project = this.project(seg[2]);
      if (seg.length === 3) {
        if (!project) return notFound("project");
        if (m === "GET") return ok(project);
        if (m === "PATCH") return this.updateProject(project, body);
      }
      if (seg.length === 4 && m === "POST" && (seg[3] === "archive" || seg[3] === "unarchive")) {
        if (!project) return notFound("project");
        return this.updateProject(project, {}, seg[3] === "archive" ? "archived" : "active");
      }
    }
    if (seg[1] === "notifications" && seg.length === 4 && seg[3] === "read" && m === "POST") return this.readOne(seg[2] ?? "");
    if (seg[1] === "ideas" && seg.length >= 3) {
      const id = seg[2] ?? "";
      if (seg.length === 4 && seg[3] === "objective" && m === "POST") return objectives.fromIdea(this, id, body);
      if (m === "GET") {
        const idea = this.state.ideas.find((i) => i.id === id);
        return idea ? ok(idea) : notFound("idea");
      }
      if (m === "PATCH") return this.updateIdea(id, body);
      if (m === "DELETE") return this.deleteIdea(id);
    }
    return undefined;
  }

  // ---- ideas -----------------------------------------------------------------------------------
  private listIdeas(q: URLSearchParams): Idea[] {
    const status = q.get("status_filter") ?? "open";
    const kind = q.get("kind");
    const project = q.get("project_id");
    const pinned = q.get("pinned");
    const text = (q.get("q") ?? "").trim().toLowerCase();
    const limit = Number(q.get("limit") ?? 200);
    return this.state.ideas
      .filter(
        (i) =>
          (status === "all" || i.status === status) &&
          (!kind || i.kind === kind) &&
          (!project || i.project_id === project) &&
          (pinned === null || String(i.pinned) === pinned) &&
          (!text || i.text.toLowerCase().includes(text)),
      )
      .sort(
        (a, b) =>
          Number(b.pinned) - Number(a.pinned) ||
          Number(a.due_at === null) - Number(b.due_at === null) ||
          (a.due_at && b.due_at ? a.due_at.localeCompare(b.due_at) : 0) ||
          b.created_at.localeCompare(a.created_at),
      )
      .slice(0, limit);
  }

  private validateIdea(body: Json, partial: boolean): Reply | Partial<Idea> {
    const out: Partial<Idea> = {};
    if ("text" in body || !partial) {
      const text = typeof body["text"] === "string" ? body["text"].trim() : "";
      if (!text || text.length > 4000) return fail(422, "invalid_request", "Write between 1 and 4000 characters.");
      out.text = text;
    }
    if ("kind" in body && body["kind"] !== null && body["kind"] !== undefined) {
      if (!["idea", "note", "todo"].includes(String(body["kind"])))
        return fail(422, "invalid_request", "Kind must be idea, note or to-do.");
      out.kind = body["kind"] as IdeaKind;
    }
    if ("project_id" in body) {
      const pid = body["project_id"];
      if (pid && !this.project(pid as string)) return notFound("project");
      out.project_id = (pid as string | null) || null;
    }
    if ("pinned" in body && typeof body["pinned"] === "boolean") out.pinned = body["pinned"];
    if ("due_at" in body) {
      const due = body["due_at"];
      if (due !== null && (typeof due !== "string" || Number.isNaN(Date.parse(due)) || !/(Z|[+-]\d\d:\d\d)$/.test(due))) {
        return fail(422, "invalid_request", "Give the due time with a timezone.");
      }
      out.due_at = due === null ? null : new Date(due).toISOString();
    }
    if ("status" in body && body["status"] !== null && body["status"] !== undefined) {
      if (!["open", "done"].includes(String(body["status"]))) return fail(422, "invalid_request", "Status must be open or done.");
      out.status = body["status"] as Idea["status"];
    }
    return out;
  }

  private createIdea(body: Json): Reply {
    const fields = this.validateIdea(body, false);
    if (isReply(fields)) return fields;
    const now = this.iso();
    const idea: Idea = {
      id: this.id("idea"),
      project_id: fields.project_id ?? null,
      kind: fields.kind ?? "idea",
      text: fields.text ?? "",
      status: "open",
      pinned: fields.pinned ?? false,
      due_at: fields.due_at ?? null,
      reminded_at: null,
      done_at: null,
      objective_id: null,
      created_at: now,
      updated_at: now,
    };
    this.state.ideas.push(idea);
    this.mark(`idea:${idea.id}`);
    this.ideaEvent("IDEA_CREATED", idea, {});
    return ok(idea, 201);
  }

  /** Apply a change to an idea (also used when one is started as an objective). */
  changeIdea(id: string, fields: Partial<Idea>, extra: Json = {}): Idea | null {
    const idea = this.state.ideas.find((i) => i.id === id);
    if (!idea) return null;
    const changed = (Object.entries(fields) as [keyof Idea, unknown][]).filter(([k, v]) => idea[k] !== v).map(([k]) => k as string);
    if (changed.length === 0) return idea;
    const next: Idea = { ...idea, ...fields, updated_at: this.iso() };
    if (changed.includes("due_at")) next.reminded_at = null;
    if (changed.includes("status")) {
      next.done_at = next.status === "done" ? this.iso() : null;
      changed.push("done_at");
    }
    this.state.ideas = this.state.ideas.map((i) => (i.id === id ? next : i));
    this.mark(`idea:${id}`);
    this.ideaEvent("IDEA_UPDATED", next, { changed: [...new Set(changed)].sort(), ...extra });
    return next;
  }

  private updateIdea(id: string, body: Json): Reply {
    if (!this.state.ideas.some((i) => i.id === id)) return notFound("idea");
    const fields = this.validateIdea(body, true);
    if (isReply(fields)) return fields;
    return ok(this.changeIdea(id, fields));
  }

  private deleteIdea(id: string): Reply {
    const idea = this.state.ideas.find((i) => i.id === id);
    if (!idea) return notFound("idea");
    this.state.ideas = this.state.ideas.filter((i) => i.id !== id);
    this.mark(`idea:${id}`);
    this.ideaEvent("IDEA_DELETED", idea, {});
    return { status: 204 };
  }

  /** One reminder for each open item whose due time has come. Returns their ids. */
  remindDue(now: Date = this.now()): string[] {
    const due = this.state.ideas.filter((i) => i.status === "open" && i.due_at && !i.reminded_at && new Date(i.due_at) <= now);
    for (const idea of due) {
      const reminded: Idea = { ...idea, reminded_at: now.toISOString() };
      this.state.ideas = this.state.ideas.map((i) => (i.id === idea.id ? reminded : i));
      this.mark(`idea:${idea.id}`);
      this.notify("idea_due", `${KIND_LABEL[idea.kind]} due: ${firstLine(idea.text)}`, idea.project_id, { idea_id: idea.id });
      this.ideaEvent("IDEA_DUE", reminded, {}, "scheduler");
    }
    return due.map((i) => i.id);
  }

  private ideaEvent(type: string, idea: Idea, extra: Json, actor = "user"): void {
    this.record({
      type,
      project_id: idea.project_id,
      actor,
      payload: {
        idea_id: idea.id,
        kind: idea.kind,
        status: idea.status,
        pinned: idea.pinned,
        due_at: idea.due_at,
        text: firstLine(idea.text),
        ...extra,
      },
    });
  }

  // ---- timeline --------------------------------------------------------------------------------
  private timeline(projectId: string | null): unknown {
    const now = this.now();
    const inScope = (pid: string | null | undefined) => !projectId || pid === projectId;
    const waiting: TimelineItem[] = [];
    const next: TimelineItem[] = [];
    const pinned: TimelineItem[] = [];
    const running: TimelineItem[] = [];
    for (const { item, waiting: needsYou } of [
      ...objectives.timelineItems(this),
      ...agents.timelineItems(this),
      ...workflows.timelineItems(this),
    ]) {
      if (inScope(item.project_id)) (needsYou ? waiting : running).push(item);
    }
    for (const idea of this.state.ideas) {
      if (idea.status !== "open" || !inScope(idea.project_id)) continue;
      const overdue = idea.due_at !== null && new Date(idea.due_at) <= now;
      const item: TimelineItem = {
        kind: "idea",
        id: idea.id,
        title: firstLine(idea.text),
        detail: KIND_LABEL[idea.kind] + (idea.pinned ? " · pinned" : ""),
        status: overdue ? "OVERDUE" : idea.due_at ? "DUE" : "OPEN",
        project_id: idea.project_id,
        at: idea.due_at ?? idea.created_at,
        ref_id: null,
        idea_kind: idea.kind,
      };
      if (idea.due_at) (overdue ? waiting : next).push(item);
      else if (idea.pinned) pinned.push(item);
    }
    const soonest = (a: TimelineItem, b: TimelineItem) => (a.at ?? "").localeCompare(b.at ?? "");
    return {
      generated_at: now.toISOString(),
      now: running.sort((a, b) => soonest(b, a)),
      waiting: waiting.sort(soonest),
      next: next.sort(soonest),
      pinned,
    };
  }

  // ---- projects, settings, notifications, search -------------------------------------------------
  createProject(body: Json, extra: Partial<Project> = {}): Reply {
    const name = typeof body["name"] === "string" ? body["name"].trim() : "";
    if (!name || name.length > 120) return fail(422, "invalid_request", "Give the project a name (up to 120 characters).");
    if (this.state.projects.some((p) => p.name.toLowerCase() === name.toLowerCase() && p.status === "active")) {
      return fail(409, "conflict", `There is already a project called '${name}'.`);
    }
    const now = this.iso();
    const project: Project = {
      id: this.id("proj"),
      name,
      slug: slugify(name),
      description: typeof body["description"] === "string" ? body["description"] : "",
      icon: typeof body["icon"] === "string" ? body["icon"] : "folder",
      status: "active",
      is_demo: false,
      settings: { permission_level: null, monthly_budget_usd: null, allowed_domains: [], linked_folders: [] },
      created_at: now,
      updated_at: now,
      ...extra,
    };
    this.state.projects.push(project);
    this.mark("projects");
    this.record({ type: "PROJECT_CREATED", project_id: project.id, payload: { name: project.name } });
    return ok(project, 201);
  }

  private updateProject(project: Project, body: Json, status?: Project["status"]): Reply {
    const next: Project = { ...project, updated_at: this.iso() };
    if (typeof body["name"] === "string" && body["name"].trim()) next.name = body["name"].trim().slice(0, 120);
    if (typeof body["description"] === "string") next.description = body["description"];
    if (typeof body["icon"] === "string") next.icon = body["icon"];
    if (body["settings"] && typeof body["settings"] === "object") next.settings = { ...project.settings, ...(body["settings"] as object) };
    if (status) next.status = status;
    this.state.projects = this.state.projects.map((p) => (p.id === project.id ? next : p));
    this.mark("projects");
    this.record({
      type: status === "archived" ? "PROJECT_ARCHIVED" : "PROJECT_UPDATED",
      project_id: project.id,
      payload: { name: next.name },
    });
    return ok(next);
  }

  private updateSettings(body: Json): Reply {
    const s = { ...this.state.settings };
    const changed: string[] = [];
    if (typeof body["display_name"] === "string") {
      s.display_name = body["display_name"].slice(0, 120);
      changed.push("display_name");
    }
    if (typeof body["onboarding_completed"] === "boolean") {
      s.onboarding_completed = body["onboarding_completed"];
      changed.push("onboarding_completed");
    }
    if (["cautious", "balanced", "permissive"].includes(String(body["default_permission_level"]))) {
      s.default_permission_level = body["default_permission_level"] as typeof s.default_permission_level;
      changed.push("default_permission_level");
    }
    s.updated_at = this.iso();
    this.state.settings = s;
    this.mark("settings");
    if (changed.length) this.record({ type: "SETTINGS_UPDATED", payload: { changed } });
    return ok(s);
  }

  private readAll(): Reply {
    const at = this.iso();
    let marked = 0;
    this.state.notifications = this.state.notifications.map((n) => (n.read_at ? n : (marked++, { ...n, read_at: at })));
    if (marked) this.mark("notifications");
    return ok({ marked });
  }

  private readOne(id: string): Reply {
    const n = this.state.notifications.find((x) => x.id === id);
    if (!n) return fail(404, "not_found", `Notification ${id} not found`);
    const read = { ...n, read_at: n.read_at ?? this.iso() };
    this.state.notifications = this.state.notifications.map((x) => (x.id === id ? read : x));
    this.mark("notifications");
    return ok(read);
  }

  private search(text: string, kinds: string[]): unknown {
    const words = text.trim().toLowerCase();
    if (!words) return { query: text, engine: "like", hits: [] };
    const want = (k: string) => kinds.length === 0 || kinds.includes(k);
    const has = (s: string) => s.toLowerCase().includes(words);
    const snippet = (s: string) => {
      const at = Math.max(0, s.toLowerCase().indexOf(words));
      const start = Math.max(0, at - 40);
      return (start > 0 ? "…" : "") + s.slice(start, start + 160);
    };
    const hit = (kind: string, id: string, project_id: string | null, title: string, body: string) => ({
      kind,
      id,
      project_id,
      title,
      snippet: snippet(body),
      score: 1,
    });
    const hits = [
      ...(want("project")
        ? this.state.projects.filter((p) => has(`${p.name} ${p.description}`)).map((p) => hit("project", p.id, p.id, p.name, p.description))
        : []),
      ...(want("objective")
        ? this.state.objectives.filter((o) => has(o.text)).map((o) => hit("objective", o.id, o.project_id, firstLine(o.text), o.text))
        : []),
      ...(want("artifact") ? files.searchArtifacts(this, words).map((a) => hit("artifact", a.id, a.project_id, a.title, a.body)) : []),
      ...(want("memory")
        ? this.state.memories
            .filter((mm) => mm.status === "active" && has(mm.content))
            .map((mm) => hit("memory", mm.id, mm.project_id, firstLine(mm.content, 80), mm.content))
        : []),
      ...(want("idea")
        ? this.state.ideas
            .filter((i) => has(i.text))
            .map((i) => hit("idea", i.id, i.project_id, firstLine(i.text) + (i.status === "done" ? " (done)" : ""), i.text))
        : []),
    ];
    return { query: text, engine: "like", hits: hits.slice(0, 30) };
  }

  // ---- events ----------------------------------------------------------------------------------
  private queryEvents(q: URLSearchParams): EventRecord[] {
    const types = new Set((q.get("types") ?? "").split(",").filter(Boolean));
    const excluded = new Set((q.get("exclude_types") ?? "").split(",").filter(Boolean));
    const project = q.get("project_id");
    const objective = q.get("objective_id");
    const run = q.get("run_id");
    const task = q.get("task_id");
    const after = Number(q.get("after_seq") ?? 0);
    const before = Number(q.get("before_seq") ?? 0);
    const limit = Math.min(Math.max(Number(q.get("limit") ?? 200), 1), 1000);
    let list = this.state.events.filter(
      (e) =>
        (!types.size || types.has(e.type)) &&
        !excluded.has(e.type) &&
        (!project || e.project_id === project) &&
        (!objective || e.objective_id === objective) &&
        (!run || e.run_id === run) &&
        (!task || e.task_id === task) &&
        e.seq > after &&
        (!before || e.seq < before),
    );
    if (q.get("newest_first") === "true") list = [...list].reverse();
    return list.slice(0, limit);
  }
}

export function isReply(v: unknown): v is Reply {
  return typeof v === "object" && v !== null && "status" in v && typeof (v as Reply).status === "number" && "body" in v;
}

/** A timeline entry from a module, and whether it waits on the person. */
export interface TimelineEntry {
  item: TimelineItem;
  waiting: boolean;
}
