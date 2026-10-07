/**
 * Project files and deliverables in the browser preview, laid out like the desktop workspace:
 * `files/` (the person's and agents' working files, writable), `artifacts/` (deliverables, read-only
 * here, each with its version history) and `temp/`.
 */
import type { Artifact } from "@nexus/schemas";
import type { PreviewServer, Reply, RouteContext } from "./server";
import { fail, notFound, ok } from "./server";
import { fileKey, MAX_VERSION_CHARS, MAX_VERSIONS_KEPT, type StoredFile } from "./state";

const AREAS = ["files", "artifacts", "temp"] as const;
const WRITABLE = new Set(["files", "temp"]);
const MAX_FILE_CHARS = 120_000;

function normalise(path: string | null): string | null {
  const raw = (path ?? ".")
    .trim()
    .replace(/\\/g, "/")
    .replace(/^\.\/?/, "")
    .replace(/\/+$/, "");
  if (raw === "" || raw === ".") return "";
  const parts = raw.split("/");
  if (parts.some((p) => p === ".." || p === "" || p.startsWith("."))) return null;
  return parts.join("/");
}

const areaOf = (path: string) => path.split("/")[0] ?? "";
const seconds = (iso: string) => Math.floor(new Date(iso).getTime() / 1000);

function sha256ish(text: string): string {
  // A stable fingerprint for display (the preview does not need a cryptographic hash).
  let a = 0x811c9dc5;
  let b = 0x01000193;
  for (let i = 0; i < text.length; i++) {
    a = Math.imul(a ^ text.charCodeAt(i), 16777619);
    b = Math.imul(b + text.charCodeAt(i), 2246822519);
  }
  return ((a >>> 0).toString(16).padStart(8, "0") + (b >>> 0).toString(16).padStart(8, "0")).repeat(4);
}

/** Every path the project has: stored files plus each deliverable's current file. */
function allEntries(srv: PreviewServer, projectId: string): { path: string; size: number; modified: number }[] {
  const out = srv.state.files
    .filter((f) => f.project_id === projectId)
    .map((f) => ({ path: f.path, size: f.content.length, modified: f.modified }));
  for (const a of srv.state.artifacts.filter((x) => x.project_id === projectId)) {
    const latest = srv.state.versions[a.id]?.at(-1);
    out.push({ path: a.path, size: latest?.content.length ?? 0, modified: seconds(a.updated_at) });
  }
  return out;
}

function listDir(srv: PreviewServer, projectId: string, dir: string): Reply {
  const entries = allEntries(srv, projectId);
  if (dir === "") {
    const present = new Set(entries.map((e) => areaOf(e.path)));
    return ok(AREAS.filter((a) => a === "files" || present.has(a)).map((a) => ({ path: a, kind: "dir", size: 0, modified: 0 })));
  }
  if (!AREAS.includes(areaOf(dir) as (typeof AREAS)[number])) return fail(422, "not_a_directory", "That is not a directory.");
  const prefix = `${dir}/`;
  const dirs = new Map<string, number>();
  const filesHere: { path: string; kind: "file"; size: number; modified: number }[] = [];
  for (const e of entries) {
    if (!e.path.startsWith(prefix)) continue;
    const rest = e.path.slice(prefix.length);
    const slash = rest.indexOf("/");
    if (slash === -1) filesHere.push({ path: e.path, kind: "file", size: e.size, modified: e.modified });
    else dirs.set(prefix + rest.slice(0, slash), Math.max(dirs.get(prefix + rest.slice(0, slash)) ?? 0, e.modified));
  }
  const dirEntries = [...dirs]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([path, modified]) => ({ path, kind: "dir" as const, size: 0, modified }));
  return ok([...dirEntries, ...filesHere.sort((a, b) => a.path.localeCompare(b.path))]);
}

export function readFile(srv: PreviewServer, projectId: string, path: string): string | null {
  const file = srv.state.files.find((f) => f.project_id === projectId && f.path === path);
  if (file) return file.content;
  const artifact = srv.state.artifacts.find((a) => a.project_id === projectId && a.path === path);
  return artifact ? (srv.state.versions[artifact.id]?.at(-1)?.content ?? "") : null;
}

export function writeFile(srv: PreviewServer, projectId: string, path: string, content: string, actor = "user"): StoredFile {
  const existing = srv.state.files.find((f) => f.project_id === projectId && f.path === path);
  const file: StoredFile = { project_id: projectId, path, content, modified: Math.floor(srv.now().getTime() / 1000) };
  srv.state.files = existing ? srv.state.files.map((f) => (f === existing ? file : f)) : [...srv.state.files, file];
  srv.mark(fileKey(file));
  srv.record({ type: "FILE_WRITTEN", project_id: projectId, actor, payload: { path, bytes: content.length, created: !existing } });
  return file;
}

/** The files an agent is shown with its task: path and (shortened) content, newest first. */
export function projectContext(srv: PreviewServer, projectId: string, budgetChars = 24_000): string {
  const parts: string[] = [];
  let used = 0;
  const files = srv.state.files
    .filter((f) => f.project_id === projectId && areaOf(f.path) === "files")
    .sort((a, b) => b.modified - a.modified);
  for (const f of files) {
    if (used >= budgetChars) {
      parts.push(`(and ${files.length - parts.length} more files not shown)`);
      break;
    }
    const room = Math.min(f.content.length, budgetChars - used, 8_000);
    parts.push(`--- ${f.path} ---\n${f.content.slice(0, room)}${room < f.content.length ? "\n(…shortened)" : ""}`);
    used += room;
  }
  return parts.join("\n\n");
}

/** Save a deliverable: a new artifact, or a new version of the one at the same path. */
export function saveArtifact(
  srv: PreviewServer,
  a: {
    project_id: string;
    name: string;
    content: string;
    objective_id?: string | null;
    task_id?: string | null;
    agent_id?: string | null;
    actor?: string;
    note?: string;
  },
): Artifact {
  const fileName =
    a.name
      .replace(/[^A-Za-z0-9._-]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 80) || "deliverable.md";
  const path = `artifacts/${fileName.includes(".") ? fileName : `${fileName}.md`}`;
  const content = a.content.slice(0, MAX_VERSION_CHARS);
  const now = srv.iso();
  const existing = srv.state.artifacts.find((x) => x.project_id === a.project_id && x.path === path);
  const artifact: Artifact = existing
    ? {
        ...existing,
        version: existing.version + 1,
        updated_at: now,
        task_id: a.task_id ?? existing.task_id,
        agent_id: a.agent_id ?? existing.agent_id,
      }
    : {
        id: srv.id("art"),
        project_id: a.project_id,
        objective_id: a.objective_id ?? null,
        task_id: a.task_id ?? null,
        agent_id: a.agent_id ?? null,
        name: path.slice("artifacts/".length),
        path,
        type: /\.md$/i.test(path) ? "markdown" : "document",
        version: 1,
        meta: {},
        created_at: now,
        updated_at: now,
      };
  srv.state.artifacts = existing
    ? srv.state.artifacts.map((x) => (x.id === artifact.id ? artifact : x))
    : [...srv.state.artifacts, artifact];
  const versions = [
    ...(srv.state.versions[artifact.id] ?? []),
    { version: artifact.version, content, created_at: now, created_by: a.agent_id ?? null, note: a.note ?? "" },
  ];
  srv.state.versions[artifact.id] = versions.slice(-MAX_VERSIONS_KEPT);
  srv.mark(`artifact:${artifact.id}`);
  srv.record({
    type: existing ? "ARTIFACT_UPDATED" : "ARTIFACT_CREATED",
    project_id: a.project_id,
    objective_id: a.objective_id ?? null,
    task_id: a.task_id ?? null,
    actor: a.actor ?? "user",
    payload: { artifact_id: artifact.id, name: artifact.name, version: artifact.version, path },
  });
  return artifact;
}

export function searchArtifacts(srv: PreviewServer, words: string): { id: string; project_id: string; title: string; body: string }[] {
  return srv.state.artifacts
    .map((a) => ({ a, body: srv.state.versions[a.id]?.at(-1)?.content ?? "" }))
    .filter(({ a, body }) => `${a.name}\n${body}`.toLowerCase().includes(words))
    .map(({ a, body }) => ({ id: a.id, project_id: a.project_id, title: a.name, body }));
}

export function route(srv: PreviewServer, { method: m, seg, q, body }: RouteContext): Reply | undefined {
  if (seg[1] === "projects" && seg[2] && (seg[3] === "files" || seg[3] === "artifacts")) {
    const project = srv.project(seg[2]);
    if (!project) return notFound("project");
    if (seg[3] === "artifacts" && m === "GET") {
      const type = q.get("type_filter");
      return ok(
        srv.state.artifacts
          .filter((a) => a.project_id === project.id && (!type || a.type === type))
          .sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
      );
    }
    const path = normalise(q.get("path"));
    if (path === null) return fail(422, "invalid_path", "That path is not allowed.");
    if (seg.length === 4 && m === "GET") return listDir(srv, project.id, path);
    if (seg.length === 5 && seg[4] === "content" && m === "GET") {
      const content = readFile(srv, project.id, path);
      return content === null ? fail(404, "not_found", "That file does not exist.") : ok({ path, content, truncated: false });
    }
    if (seg.length === 5 && seg[4] === "content" && m === "PUT") {
      if (!WRITABLE.has(areaOf(path)) || !path.includes("/"))
        return fail(403, "read_only", "Only files under files/ or temp/ can be changed.");
      const content = typeof body["content"] === "string" ? body["content"] : "";
      if (content.length > MAX_FILE_CHARS)
        return fail(413, "too_large", "That file is too large for the browser preview (120,000 characters at most).");
      const file = writeFile(srv, project.id, path, content);
      return ok({ path: file.path, kind: "file", size: file.content.length, modified: file.modified });
    }
    if (seg.length === 4 && m === "DELETE") {
      if (!WRITABLE.has(areaOf(path))) return fail(403, "read_only", "Only files under files/ or temp/ can be deleted.");
      const gone = srv.state.files.filter((f) => f.project_id === project.id && (f.path === path || f.path.startsWith(`${path}/`)));
      if (gone.length === 0) return fail(404, "not_found", "That file does not exist.");
      srv.state.files = srv.state.files.filter((f) => !gone.includes(f));
      for (const f of gone) srv.mark(fileKey(f));
      srv.record({ type: "FILE_DELETED", project_id: project.id, payload: { path, deleted: true } });
      return ok({ deleted: path });
    }
  }
  if (seg[1] === "artifacts" && seg[2]) {
    const artifact = srv.state.artifacts.find((a) => a.id === seg[2]);
    if (!artifact) return notFound("deliverable");
    const versions = srv.state.versions[artifact.id] ?? [];
    if (seg.length === 3 && m === "GET") return ok(artifact);
    if (seg[3] === "versions" && m === "GET") {
      return ok(
        [...versions]
          .reverse()
          .map((v) => ({
            version: v.version,
            created_at: v.created_at,
            created_by: v.created_by,
            note: v.note,
            sha256: sha256ish(v.content),
            size: v.content.length,
          })),
      );
    }
    if (seg[3] === "content" && m === "GET") {
      const wanted = Number(q.get("version") ?? artifact.version);
      const v = versions.find((x) => x.version === wanted) ?? versions.at(-1);
      if (!v) return fail(404, "not_found", "That version is no longer kept in the browser preview.");
      return ok({ artifact, content: v.content, truncated: false, version: v.version });
    }
  }
  return undefined;
}
