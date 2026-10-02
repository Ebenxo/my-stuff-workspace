/**
 * The browser preview's stand-in for the NEXUS API.
 *
 * The preview build (`pnpm --filter @nexus/web build:preview`) runs the real web app with no Python
 * API behind it. Requests to the API are answered here instead, in the page: ideas, notes and to-dos,
 * the timeline built from them, projects, settings, notifications and the activity history work for
 * real and are saved (see `persist.ts`). Anything that needs agents, models, tools or workflows
 * answers with a plain explanation that it needs NEXUS running on the person's computer.
 *
 * Pure: no `window`, no timers. `install.ts` wires it to `fetch` and to storage.
 */
import type { EventRecord, Idea, IdeaKind, Notification, Project, TimelineItem, UserSettings } from "@nexus/schemas";

export const PREVIEW_ORIGIN = "https://nexus.preview";
const MAX_EVENTS = 400;
const MAX_NOTIFICATIONS = 100;
const KIND_LABEL: Record<IdeaKind, string> = { idea: "Idea", note: "Note", todo: "To-do" };

export const NEEDS_DESKTOP =
  "This part needs NEXUS running on your computer. In this browser preview, the Timeline, Ideas & notes, projects and settings work; agents, models, tools and workflows do not.";

export interface PreviewState {
  settings: UserSettings;
  projects: Project[];
  ideas: Idea[];
  notifications: Notification[];
  events: EventRecord[];
  seq: number;
}

/** Which stored documents a change touched, so storage writes only those. */
export type DirtyKey = "settings" | "projects" | "notifications" | "events" | `idea:${string}`;

export interface Reply {
  status: number;
  body?: unknown;
}

const ok = (body: unknown, status = 200): Reply => ({ status, body });
const fail = (status: number, code: string, message: string): Reply => ({ status, body: { error: { code, message } } });
const needsDesktop = (): Reply => fail(501, "needs_desktop", NEEDS_DESKTOP);

/** GET endpoints that list things; in the preview they are empty rather than unavailable. */
const EMPTY_LISTS = new Set([
  "/api/agents",
  "/api/approvals",
  "/api/approvals/grants",
  "/api/mcp/servers",
  "/api/memory",
  "/api/memory/search",
  "/api/models",
  "/api/objectives",
  "/api/providers",
  "/api/providers/kinds",
  "/api/runs",
  "/api/schedules",
  "/api/tool-calls",
  "/api/tools",
  "/api/workflow-runs",
  "/api/workflows",
]);

export function emptyState(now: Date): PreviewState {
  return {
    settings: {
      display_name: "",
      workspace_root: "(your computer)",
      default_permission_level: "balanced",
      onboarding_completed: true,
      preferences: {},
      updated_at: now.toISOString(),
    },
    projects: [],
    ideas: [],
    notifications: [],
    events: [],
    seq: 0,
  };
}

function newId(prefix: string): string {
  const rand = Math.random().toString(36).slice(2, 10);
  return `${prefix}_${Date.now().toString(36)}${rand}`;
}

function firstLine(text: string, max = 120): string {
  return (text.trim().split("\n")[0] ?? "").slice(0, max) || "Untitled";
}

function slugify(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "project";
}

type Json = Record<string, unknown>;

export class PreviewServer {
  readonly dirty = new Set<DirtyKey>();
  private listeners = new Set<(e: EventRecord) => void>();

  constructor(
    public state: PreviewState,
    private clock: () => Date = () => new Date(),
  ) {}

  onEvent(fn: (e: EventRecord) => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  /** Events after ``seq``, oldest first (for a stream that resumes). */
  eventsAfter(seq: number): EventRecord[] {
    return this.state.events.filter((e) => e.seq > seq);
  }

  handle(method: string, url: URL, body: unknown): Reply {
    const path = url.pathname.replace(/\/+$/, "") || "/";
    const q = url.searchParams;
    const m = method.toUpperCase();
    const seg = path.split("/").filter(Boolean); // ["api", ...]

    if (m === "GET" && EMPTY_LISTS.has(path)) return ok([]);
    switch (`${m} ${path}`) {
      case "GET /api/health/ping":
        return ok({ ok: true });
      case "GET /api/health":
        return ok({
          status: "ok",
          version: "preview",
          checks: [
            { name: "preview", label: "Browser preview", status: "ok", detail: "Running in your browser. Agents and models need NEXUS on your computer.", data: {} },
          ],
        });
      case "GET /api/settings":
        return ok(this.state.settings);
      case "PATCH /api/settings":
        return this.updateSettings(body as Json);
      case "GET /api/projects":
        return ok(this.state.projects.filter((p) => !q.get("status_filter") || p.status === q.get("status_filter")));
      case "POST /api/projects":
        return this.createProject(body as Json);
      case "GET /api/notifications":
        return ok(this.state.notifications.filter((n) => q.get("unread_only") !== "true" || !n.read_at));
      case "GET /api/notifications/unread-count":
        return ok({ count: this.state.notifications.filter((n) => !n.read_at).length });
      case "POST /api/notifications/read-all":
        return this.readAll();
      case "GET /api/events":
        return ok(this.queryEvents(q));
      case "GET /api/events/verify":
        return ok({ ok: true, chains_checked: 0, events_checked: 0, first_bad_seq: null, detail: "The browser preview keeps a simple history without the hash chain." });
      case "GET /api/memory/stats":
        return ok({ active: 0, pending: 0, deleted: 0 });
      case "GET /api/search":
        return ok(this.search(q.get("q") ?? ""));
      case "GET /api/ideas":
        return ok(this.listIdeas(q));
      case "POST /api/ideas":
        return this.createIdea(body as Json);
      case "GET /api/ideas/due-count":
        return ok({ count: this.state.ideas.filter((i) => i.status === "open" && i.due_at && new Date(i.due_at) <= this.clock()).length });
      case "GET /api/timeline":
        return ok(this.timeline(q.get("project_id")));
    }
    if (seg[1] === "projects" && seg.length === 3) {
      const project = this.state.projects.find((p) => p.id === seg[2]);
      if (m === "GET") return project ? ok(project) : fail(404, "not_found", "That project does not exist.");
    }
    if (seg[1] === "notifications" && seg.length === 4 && seg[3] === "read" && m === "POST") return this.readOne(seg[2] ?? "");
    if (seg[1] === "ideas" && seg.length >= 3) {
      const id = seg[2] ?? "";
      if (seg.length === 4 && seg[3] === "objective") return needsDesktop();
      if (m === "GET") {
        const idea = this.state.ideas.find((i) => i.id === id);
        return idea ? ok(idea) : fail(404, "not_found", "That idea does not exist.");
      }
      if (m === "PATCH") return this.updateIdea(id, body as Json);
      if (m === "DELETE") return this.deleteIdea(id);
    }
    return needsDesktop();
  }

  // ---- ideas ---------------------------------------------------------------------------------
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

  private validate(body: Json, partial: boolean): Reply | Partial<Idea> {
    const out: Partial<Idea> = {};
    if ("text" in body || !partial) {
      const text = typeof body["text"] === "string" ? body["text"].trim() : "";
      if (!text || text.length > 4000) return fail(422, "invalid_request", "Write between 1 and 4000 characters.");
      out.text = text;
    }
    if ("kind" in body && body["kind"] !== null && body["kind"] !== undefined) {
      if (!["idea", "note", "todo"].includes(String(body["kind"]))) return fail(422, "invalid_request", "Kind must be idea, note or to-do.");
      out.kind = body["kind"] as IdeaKind;
    }
    if ("project_id" in body) {
      const pid = body["project_id"];
      if (pid && !this.state.projects.some((p) => p.id === pid)) return fail(404, "not_found", "That project does not exist.");
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
    const fields = this.validate(body ?? {}, false);
    if (isReply(fields)) return fields;
    const now = this.clock().toISOString();
    const idea: Idea = {
      id: newId("idea"),
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
    this.dirty.add(`idea:${idea.id}`);
    this.emit("IDEA_CREATED", idea, {});
    return ok(idea, 201);
  }

  private updateIdea(id: string, body: Json): Reply {
    const idea = this.state.ideas.find((i) => i.id === id);
    if (!idea) return fail(404, "not_found", "That idea does not exist.");
    const fields = this.validate(body ?? {}, true);
    if (isReply(fields)) return fields;
    const changed: string[] = [];
    for (const [k, v] of Object.entries(fields) as [keyof Idea, unknown][]) {
      if (idea[k] !== v) changed.push(k);
    }
    if (changed.length === 0) return ok(idea);
    const next: Idea = { ...idea, ...fields, updated_at: this.clock().toISOString() };
    if (changed.includes("due_at")) next.reminded_at = null;
    if (changed.includes("status")) {
      next.done_at = next.status === "done" ? this.clock().toISOString() : null;
      changed.push("done_at");
    }
    this.state.ideas = this.state.ideas.map((i) => (i.id === id ? next : i));
    this.dirty.add(`idea:${id}`);
    this.emit("IDEA_UPDATED", next, { changed: [...new Set(changed)].sort() });
    return ok(next);
  }

  private deleteIdea(id: string): Reply {
    const idea = this.state.ideas.find((i) => i.id === id);
    if (!idea) return fail(404, "not_found", "That idea does not exist.");
    this.state.ideas = this.state.ideas.filter((i) => i.id !== id);
    this.dirty.add(`idea:${id}`);
    this.emit("IDEA_DELETED", idea, {});
    return { status: 204 };
  }

  /** One reminder for each open item whose due time has come. Returns their ids. */
  remindDue(now: Date = this.clock()): string[] {
    const due = this.state.ideas.filter((i) => i.status === "open" && i.due_at && !i.reminded_at && new Date(i.due_at) <= now);
    for (const idea of due) {
      const reminded: Idea = { ...idea, reminded_at: now.toISOString() };
      this.state.ideas = this.state.ideas.map((i) => (i.id === idea.id ? reminded : i));
      this.dirty.add(`idea:${idea.id}`);
      this.notify("idea_due", `${KIND_LABEL[idea.kind]} due: ${firstLine(idea.text)}`, idea.project_id, { idea_id: idea.id });
      this.emit("IDEA_DUE", reminded, {}, "scheduler");
    }
    return due.map((i) => i.id);
  }

  // ---- timeline ------------------------------------------------------------------------------
  private timeline(projectId: string | null): unknown {
    const now = this.clock();
    const waiting: TimelineItem[] = [];
    const next: TimelineItem[] = [];
    const pinned: TimelineItem[] = [];
    for (const idea of this.state.ideas) {
      if (idea.status !== "open" || (projectId && idea.project_id !== projectId)) continue;
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
    const byTime = (a: TimelineItem, b: TimelineItem) => (a.at ?? "").localeCompare(b.at ?? "");
    return { generated_at: now.toISOString(), now: [], waiting: waiting.sort(byTime), next: next.sort(byTime), pinned };
  }

  // ---- projects, settings, notifications, search -----------------------------------------------
  private createProject(body: Json): Reply {
    const name = typeof body?.["name"] === "string" ? body["name"].trim() : "";
    if (!name || name.length > 120) return fail(422, "invalid_request", "Give the project a name (up to 120 characters).");
    const now = this.clock().toISOString();
    const project: Project = {
      id: newId("proj"),
      name,
      slug: slugify(name),
      description: typeof body["description"] === "string" ? body["description"] : "",
      icon: "folder",
      status: "active",
      is_demo: false,
      settings: { permission_level: null, monthly_budget_usd: null, allowed_domains: [], linked_folders: [] },
      created_at: now,
      updated_at: now,
    };
    this.state.projects.push(project);
    this.dirty.add("projects");
    this.record({ type: "PROJECT_CREATED", project_id: project.id, payload: { name: project.name } });
    return ok(project, 201);
  }

  private updateSettings(body: Json): Reply {
    const s = { ...this.state.settings };
    const changed: string[] = [];
    if (typeof body?.["display_name"] === "string") {
      s.display_name = body["display_name"].slice(0, 120);
      changed.push("display_name");
    }
    if (typeof body?.["onboarding_completed"] === "boolean") {
      s.onboarding_completed = body["onboarding_completed"];
      changed.push("onboarding_completed");
    }
    if (["cautious", "balanced", "permissive"].includes(String(body?.["default_permission_level"]))) {
      s.default_permission_level = body["default_permission_level"] as UserSettings["default_permission_level"];
      changed.push("default_permission_level");
    }
    s.updated_at = this.clock().toISOString();
    this.state.settings = s;
    this.dirty.add("settings");
    if (changed.length) this.record({ type: "SETTINGS_UPDATED", payload: { changed } });
    return ok(s);
  }

  private notify(kind: string, title: string, projectId: string | null, ref: Json): void {
    const n: Notification = { id: newId("ntf"), kind, title: title.slice(0, 200), body: "", project_id: projectId, ref, read_at: null, created_at: this.clock().toISOString() };
    this.state.notifications = [n, ...this.state.notifications].slice(0, MAX_NOTIFICATIONS);
    this.dirty.add("notifications");
    this.record({ type: "NOTIFICATION_CREATED", project_id: projectId, payload: { notification_id: n.id, kind, title: n.title } });
  }

  private readAll(): Reply {
    const at = this.clock().toISOString();
    let marked = 0;
    this.state.notifications = this.state.notifications.map((n) => (n.read_at ? n : (marked++, { ...n, read_at: at })));
    if (marked) this.dirty.add("notifications");
    return ok({ marked });
  }

  private readOne(id: string): Reply {
    const n = this.state.notifications.find((x) => x.id === id);
    if (!n) return fail(404, "not_found", `Notification ${id} not found`);
    const read = { ...n, read_at: n.read_at ?? this.clock().toISOString() };
    this.state.notifications = this.state.notifications.map((x) => (x.id === id ? read : x));
    this.dirty.add("notifications");
    return ok(read);
  }

  private search(text: string): unknown {
    const words = text.trim().toLowerCase();
    const hits = !words
      ? []
      : [
          ...this.state.projects
            .filter((p) => `${p.name} ${p.description}`.toLowerCase().includes(words))
            .map((p) => ({ kind: "project", id: p.id, project_id: p.id, title: p.name, snippet: p.description, score: 1 })),
          ...this.state.ideas
            .filter((i) => i.text.toLowerCase().includes(words))
            .map((i) => ({
              kind: "idea",
              id: i.id,
              project_id: i.project_id,
              title: firstLine(i.text) + (i.status === "done" ? " (done)" : ""),
              snippet: i.text.slice(0, 160),
              score: 1,
            })),
        ];
    return { query: text, engine: "like", hits };
  }

  // ---- events --------------------------------------------------------------------------------
  private queryEvents(q: URLSearchParams): EventRecord[] {
    const types = new Set((q.get("types") ?? "").split(",").filter(Boolean));
    const excluded = new Set((q.get("exclude_types") ?? "").split(",").filter(Boolean));
    const project = q.get("project_id");
    const after = Number(q.get("after_seq") ?? 0);
    const before = Number(q.get("before_seq") ?? 0);
    const limit = Math.min(Math.max(Number(q.get("limit") ?? 200), 1), 1000);
    let list = this.state.events.filter(
      (e) =>
        (!types.size || types.has(e.type)) &&
        !excluded.has(e.type) &&
        (!project || e.project_id === project) &&
        e.seq > after &&
        (!before || e.seq < before),
    );
    if (q.get("newest_first") === "true") list = [...list].reverse();
    return list.slice(0, limit);
  }

  private emit(type: string, idea: Idea, extra: Json, actor = "user"): void {
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

  private record(e: { type: string; project_id?: string | null; actor?: string; payload: Json }): void {
    const seq = this.state.seq + 1;
    this.state.seq = seq;
    const event: EventRecord = {
      seq,
      id: `evt_${seq}`,
      ts: this.clock().toISOString(),
      type: e.type,
      project_id: e.project_id ?? null,
      objective_id: null,
      task_id: null,
      run_id: null,
      agent_id: null,
      actor: e.actor ?? "user",
      payload: e.payload,
      prev_hash: "",
      hash: "",
    };
    this.state.events = [...this.state.events, event].slice(-MAX_EVENTS);
    this.dirty.add("events");
    for (const fn of this.listeners) fn(event);
  }

  /** The first entry in a fresh preview's history. */
  started(): void {
    this.record({ type: "SYSTEM_STARTED", actor: "system", payload: { version: "0.1.0, browser preview" } });
  }
}

function isReply(v: unknown): v is Reply {
  return typeof v === "object" && v !== null && "status" in v && typeof (v as Reply).status === "number" && "body" in v;
}
