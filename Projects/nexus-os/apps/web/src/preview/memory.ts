/**
 * Memory in the browser preview: what NEXUS remembers, per project or everywhere.
 *
 * The person writes memories; agents suggest them (the person confirms or dismisses). Search ranks
 * with the same visible breakdown as the desktop (overlap of words stands in for the desktop's
 * embeddings). Credentials and personal identifiers are refused, as on the desktop.
 */
import type { MemoryHit, MemoryItem, MemorySource } from "@nexus/schemas";
import type { Json, PreviewServer, Reply, RouteContext } from "./server";
import { fail, notFound, ok } from "./server";

const WEIGHTS = { semantic: 0.45, keyword: 0.15, recency: 0.15, importance: 0.15, task: 0.1 };
const TAU_DAYS: Record<string, number> = { project: 30, global: 180, conversation: 7 };
const BANDS: Record<MemorySource["kind"], number> = { user: 0.8, agent: 0.5, objective: 0.4, summary: 0.4 };
const MAX_CONTENT = 4000;
const STOP = new Set(
  "a an and are as at be but by for from has have in is it its of on or that the this to was were will with you your we our".split(" "),
);

export const words = (text: string): string[] =>
  text
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((w) => w.length > 1 && !STOP.has(w));

function hash(text: string): string {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return (h >>> 0).toString(16).padStart(8, "0");
}

/** Categories of sensitive data in ``text`` (empty when it is fine to remember). */
export function sensitive(text: string): string[] {
  const found = new Set<string>();
  if (/-----BEGIN [A-Z ]*PRIVATE KEY-----/.test(text)) found.add("private key");
  if (/\bsk-(ant-)?[A-Za-z0-9_-]{20,}|\bAIza[0-9A-Za-z_-]{30,}/.test(text)) found.add("API key");
  if (/\b(ghp|gho|github_pat|xox[abp])_?[A-Za-z0-9_]{20,}/.test(text) || /\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\./.test(text))
    found.add("access token");
  if (/\bAKIA[0-9A-Z]{16}\b/.test(text)) found.add("cloud credential");
  if (/\b(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*\S{6,}/i.test(text)) found.add("password or secret");
  for (const m of text.matchAll(/(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])/g)) {
    const digits = m[0].replace(/\D/g, "");
    if (digits.length >= 13 && "23456".includes(digits[0] ?? "") && new Set(digits).size > 1 && luhn(digits))
      found.add("payment card number");
  }
  if (/\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b/.test(text)) found.add("national identity number");
  return [...found];
}

function luhn(digits: string): boolean {
  let total = 0;
  [...digits].reverse().forEach((ch, i) => {
    let d = Number(ch);
    if (i % 2 === 1) {
      d *= 2;
      if (d > 9) d -= 9;
    }
    total += d;
  });
  return total % 10 === 0;
}

const refused = (categories: string[]): Reply =>
  fail(
    422,
    "sensitive_data",
    `Not remembered: it looks like it contains sensitive data (${categories.join(", ")}). Memories are kept and shown to future agents, so credentials and personal identifiers are never stored. Remember the non-sensitive part instead.`,
  );

const preview = (item: Pick<MemoryItem, "content">) => item.content.replace(/\s+/g, " ").slice(0, 120);

function save(srv: PreviewServer, item: MemoryItem): MemoryItem {
  srv.state.memories = srv.state.memories.some((m) => m.id === item.id)
    ? srv.state.memories.map((m) => (m.id === item.id ? item : m))
    : [...srv.state.memories, item];
  srv.mark(`mem:${item.id}`);
  return item;
}

function cleanTags(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  return [
    ...new Set(
      raw
        .filter((t): t is string => typeof t === "string")
        .map((t) => t.trim().toLowerCase().slice(0, 40))
        .filter(Boolean),
    ),
  ].slice(0, 12);
}

/** Add a memory. Agents' suggestions wait for the person (status "pending"). */
export function remember(
  srv: PreviewServer,
  m: {
    content: string;
    project_id: string | null;
    scope: "project" | "global";
    tags?: string[];
    source: MemorySource;
    pinned?: boolean;
    pending?: boolean;
  },
): MemoryItem | Reply {
  const content = m.content.trim().slice(0, MAX_CONTENT);
  if (!content) return fail(422, "invalid_request", "Write what to remember.");
  const categories = sensitive(content);
  if (categories.length) {
    srv.record({
      type: "MEMORY_REJECTED",
      project_id: m.project_id,
      actor: m.source.kind === "user" ? "user" : (m.source.agent ?? "agent"),
      payload: { categories },
    });
    return refused(categories);
  }
  const contentHash = hash(content.toLowerCase());
  const duplicate = srv.state.memories.find(
    (x) => x.status !== "deleted" && x.content_hash === contentHash && x.project_id === m.project_id && x.scope === m.scope,
  );
  if (duplicate) return duplicate;
  const now = srv.iso();
  const item: MemoryItem = {
    id: srv.id("mem"),
    scope: m.scope,
    project_id: m.scope === "global" ? null : m.project_id,
    content,
    summary: "",
    importance: m.pinned ? 1 : BANDS[m.source.kind],
    source: m.source,
    tags: cleanTags(m.tags),
    status: m.pending ? "pending" : "active",
    content_hash: contentHash,
    access_count: 0,
    last_accessed_at: null,
    merged_into: null,
    created_at: now,
    updated_at: now,
  };
  save(srv, item);
  srv.record({
    type: "MEMORY_CREATED",
    project_id: item.project_id,
    actor: m.source.kind === "user" ? "user" : (m.source.agent ?? "agent"),
    payload: { id: item.id, status: item.status, preview: preview(item) },
  });
  return item;
}

// ---- recall -----------------------------------------------------------------------------------------

function score(srv: PreviewServer, query: string, items: MemoryItem[], objectiveId?: string | null): MemoryHit[] {
  const q = [...new Set(words(query))];
  if (!q.length) return [];
  const docs = items.map((i) => words(`${i.content} ${i.tags.join(" ")}`));
  // Keyword: BM25 over these items, scaled by the best.
  const n = docs.length;
  const avgdl = docs.reduce((s, d) => s + d.length, 0) / (n || 1) || 1;
  const df = new Map<string, number>();
  for (const d of docs) for (const w of new Set(d)) df.set(w, (df.get(w) ?? 0) + 1);
  const bm = docs.map((d) => {
    const tf = new Map<string, number>();
    for (const w of d) tf.set(w, (tf.get(w) ?? 0) + 1);
    return q.reduce((s, w) => {
      const f = tf.get(w) ?? 0;
      if (!f) return s;
      const idf = Math.log(1 + (n - (df.get(w) ?? 0) + 0.5) / ((df.get(w) ?? 0) + 0.5));
      return s + (idf * f * 2.2) / (f + 1.2 * (1 - 0.75 + (0.75 * d.length) / avgdl));
    }, 0);
  });
  const best = Math.max(...bm, 0) || 1;
  const now = srv.now().getTime();
  const hits: MemoryHit[] = [];
  items.forEach((item, i) => {
    const d = new Set(docs[i]);
    const overlap = q.filter((w) => d.has(w)).length;
    const semantic = overlap ? overlap / Math.sqrt(q.length * Math.max(d.size, 1)) : 0;
    const keyword = (bm[i] ?? 0) / best;
    if (keyword <= 0 && semantic < 0.12) return;
    const ageDays = (now - new Date(item.last_accessed_at ?? item.updated_at).getTime()) / 86_400_000;
    const recency = Math.exp(-Math.max(ageDays, 0) / (TAU_DAYS[item.scope] ?? 30));
    const task = objectiveId && item.source.objective_id === objectiveId ? 1 : item.tags.some((t) => q.includes(t)) ? 0.5 : 0;
    const parts = { semantic, keyword, recency, importance: item.importance, task };
    const total = (Object.keys(WEIGHTS) as (keyof typeof WEIGHTS)[]).reduce((s, k) => s + WEIGHTS[k] * parts[k], 0);
    const round = (x: number) => Math.round(x * 1000) / 1000;
    hits.push({
      item,
      score: {
        semantic: round(semantic),
        keyword: round(keyword),
        recency: round(recency),
        importance: round(item.importance),
        task: round(task),
        total: round(total),
      },
    });
  });
  return hits.sort((a, b) => b.score.total - a.score.total);
}

function inScope(item: MemoryItem, projectId: string | null, scopes: string[]): boolean {
  if (!scopes.includes(item.scope)) return false;
  return item.scope === "global" || !projectId || item.project_id === projectId;
}

/** What an agent working in this project is shown: pinned facts, then the best matches for the task. */
export function memoryContext(srv: PreviewServer, projectId: string, query = "", limit = 8): string {
  const active = srv.state.memories.filter((m) => m.status === "active" && inScope(m, projectId, ["project", "global"]));
  const pinned = active.filter((m) => m.importance >= 1 && m.project_id === projectId);
  const matched = query ? score(srv, query, active).map((h) => h.item) : [];
  // The person's own notes matter even when no word matches (preferences, standing facts).
  const theirs = active
    .filter((m) => m.source.kind === "user")
    .sort((a, b) => b.importance - a.importance || b.updated_at.localeCompare(a.updated_at))
    .slice(0, 3);
  const chosen = [...new Map([...pinned, ...matched, ...theirs].map((m) => [m.id, m])).values()].slice(0, limit);
  if (chosen.length) {
    const at = srv.iso();
    srv.state.memories = srv.state.memories.map((m) =>
      chosen.some((c) => c.id === m.id) ? { ...m, access_count: m.access_count + 1, last_accessed_at: at } : m,
    );
    for (const c of chosen) srv.mark(`mem:${c.id}`);
  }
  return chosen.map((m) => `- ${m.content.replace(/\s+/g, " ").slice(0, 500)}`).join("\n");
}

// ---- compression --------------------------------------------------------------------------------------

function compress(srv: PreviewServer, projectId: string, olderThanDays: number): unknown {
  const before = srv.now().getTime() - olderThanDays * 86_400_000;
  const cands = srv.state.memories.filter(
    (m) =>
      m.status === "active" &&
      m.scope === "project" &&
      m.project_id === projectId &&
      m.importance <= 0.5 &&
      m.access_count <= 1 &&
      new Date(m.updated_at).getTime() <= before,
  );
  const groups: MemoryItem[][] = [];
  for (const item of cands) {
    const w = new Set(words(item.content));
    const fits = (g: MemoryItem[]) =>
      g.length < 12 &&
      g.some(
        (o) =>
          o.tags.some((t) => item.tags.includes(t)) ||
          (() => {
            const ow = new Set(words(o.content));
            const shared = [...w].filter((x) => ow.has(x)).length;
            return shared / Math.sqrt(Math.max(w.size, 1) * Math.max(ow.size, 1)) >= 0.28;
          })(),
      );
    const g = groups.find(fits);
    if (g) g.push(item);
    else groups.push([item]);
  }
  const summaries: string[] = [];
  let compressed = 0;
  for (const g of groups.filter((x) => x.length >= 3)) {
    const sentences = g.map((m) => (m.content.split(/(?<=[.!?])\s+|\n+/)[0] ?? "").trim()).filter(Boolean);
    const text = sentences.join(" ").slice(0, 700);
    const made = remember(srv, {
      content: text,
      project_id: projectId,
      scope: "project",
      tags: [...new Set(g.flatMap((m) => m.tags))],
      source: { kind: "summary" },
    });
    if (!("id" in made)) continue;
    for (const m of g) save(srv, { ...m, status: "deleted", merged_into: made.id, updated_at: srv.iso() });
    summaries.push(made.id);
    compressed += g.length;
    srv.record({ type: "MEMORY_COMPRESSED", project_id: projectId, payload: { id: made.id, merged: g.length, preview: preview(made) } });
  }
  return { project_id: projectId, groups: summaries.length, compressed, summaries };
}

// ---- endpoints ------------------------------------------------------------------------------------------

function list(srv: PreviewServer, q: URLSearchParams): MemoryItem[] {
  const project = q.get("project_id");
  const scope = q.get("scope");
  const status = q.get("status_filter") ?? "active";
  const tag = q.get("tag")?.toLowerCase();
  const source = q.get("source");
  const text = (q.get("q") ?? "").trim().toLowerCase();
  const limit = Math.min(Math.max(Number(q.get("limit") ?? 100), 1), 500);
  const offset = Math.max(Number(q.get("offset") ?? 0), 0);
  return srv.state.memories
    .filter(
      (m) =>
        m.status === status &&
        (!scope || m.scope === scope) &&
        (!project || m.project_id === project || (scope !== "project" && m.scope === "global")) &&
        (!tag || m.tags.includes(tag)) &&
        (!source || m.source.kind === source) &&
        (!text || m.content.toLowerCase().includes(text)),
    )
    .sort((a, b) => b.importance - a.importance || b.updated_at.localeCompare(a.updated_at))
    .slice(offset, offset + limit);
}

function update(srv: PreviewServer, item: MemoryItem, body: Json): Reply {
  if (item.status === "deleted") return fail(409, "conflict", "Restore this memory before editing it.");
  const next: MemoryItem = { ...item, updated_at: srv.iso() };
  if (typeof body["content"] === "string") {
    const content = body["content"].trim().slice(0, MAX_CONTENT);
    if (!content) return fail(422, "invalid_request", "Write what to remember.");
    const categories = sensitive(content);
    if (categories.length) return refused(categories);
    next.content = content;
    next.content_hash = hash(content.toLowerCase());
  }
  if ("tags" in body && body["tags"] !== null) next.tags = cleanTags(body["tags"]);
  if (typeof body["pinned"] === "boolean") next.importance = body["pinned"] ? 1 : BANDS[item.source.kind];
  save(srv, next);
  srv.record({
    type: "MEMORY_UPDATED",
    project_id: next.project_id,
    payload: {
      id: next.id,
      change: typeof body["pinned"] === "boolean" ? (body["pinned"] ? "pinned" : "unpinned") : "edited",
      preview: preview(next),
    },
  });
  return ok(next);
}

function setStatus(srv: PreviewServer, item: MemoryItem, status: MemoryItem["status"], change: string): MemoryItem {
  const next = save(srv, { ...item, status, updated_at: srv.iso(), ...(status === "active" ? { merged_into: null } : {}) });
  if (status === "deleted") srv.record({ type: "MEMORY_DELETED", project_id: item.project_id, payload: { id: item.id, reason: change } });
  else srv.record({ type: "MEMORY_UPDATED", project_id: item.project_id, payload: { id: item.id, change, preview: preview(item) } });
  return next;
}

export function route(srv: PreviewServer, { method: m, path, seg, q, body }: RouteContext): Reply | undefined {
  if (seg[1] !== "memory") return undefined;
  switch (`${m} ${path}`) {
    case "GET /api/memory":
      return ok(list(srv, q));
    case "GET /api/memory/stats": {
      const project = q.get("project_id");
      const mine = srv.state.memories.filter((x) => !project || x.project_id === project || x.scope === "global");
      return ok({
        active: mine.filter((x) => x.status === "active").length,
        pending: mine.filter((x) => x.status === "pending").length,
        deleted: mine.filter((x) => x.status === "deleted").length,
      });
    }
    case "GET /api/memory/search": {
      const scope = q.get("scope") ?? "any";
      const scopes = scope === "any" ? ["project", "global"] : [scope];
      const items = srv.state.memories.filter((x) => x.status === "active" && inScope(x, q.get("project_id"), scopes));
      return ok(score(srv, q.get("q") ?? "", items).slice(0, Math.min(Math.max(Number(q.get("k") ?? 10), 1), 50)));
    }
    case "POST /api/memory": {
      const scope = body["scope"] === "global" ? "global" : "project";
      const projectId = typeof body["project_id"] === "string" ? body["project_id"] : null;
      if (scope === "project" && !srv.project(projectId)) return notFound("project");
      const made = remember(srv, {
        content: typeof body["content"] === "string" ? body["content"] : "",
        project_id: projectId,
        scope,
        tags: cleanTags(body["tags"]),
        source: { kind: "user" },
        pinned: body["pinned"] === true,
      });
      return "id" in made ? ok(made, 201) : made;
    }
    case "POST /api/memory/compress": {
      const projectId = String(body["project_id"] ?? "");
      if (!srv.project(projectId)) return notFound("project");
      const days = Number(body["older_than_days"] ?? 30);
      return ok(compress(srv, projectId, Number.isFinite(days) ? Math.min(Math.max(days, 0), 3650) : 30));
    }
  }
  const item = srv.state.memories.find((x) => x.id === seg[2]);
  if (!item) return notFound("memory");
  if (seg.length === 3) {
    if (m === "GET") return ok(item);
    if (m === "PATCH") return update(srv, item, body);
    if (m === "DELETE") {
      if (q.get("purge") === "true") {
        srv.state.memories = srv.state.memories.filter((x) => x.id !== item.id);
        srv.mark(`mem:${item.id}`);
        srv.record({ type: "MEMORY_DELETED", project_id: item.project_id, payload: { id: item.id, reason: "purged" } });
      } else if (item.status !== "deleted") setStatus(srv, item, "deleted", "deleted");
      return { status: 204 };
    }
  }
  if (m !== "POST") return undefined;
  switch (seg[3]) {
    case "confirm":
      if (item.status !== "pending") return fail(409, "conflict", "Only a suggested memory can be confirmed.");
      return ok(setStatus(srv, item, "active", "confirmed"));
    case "dismiss":
      if (item.status !== "pending") return fail(409, "conflict", "Only a suggested memory can be dismissed.");
      return ok(setStatus(srv, item, "deleted", "dismissed"));
    case "restore":
      if (item.status !== "deleted") return fail(409, "conflict", "Only a deleted memory can be restored.");
      return ok(setStatus(srv, item, "active", "restored"));
    case "undo-compression": {
      const originals = srv.state.memories.filter((x) => x.merged_into === item.id);
      if (item.source.kind !== "summary" || !originals.length) return fail(409, "conflict", "This memory is not a compression summary.");
      const restored = originals.map((o) => setStatus(srv, o, "active", "restored"));
      setStatus(srv, item, "deleted", "deleted");
      return ok(restored);
    }
  }
  return undefined;
}
