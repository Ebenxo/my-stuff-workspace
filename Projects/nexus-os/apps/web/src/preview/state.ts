/**
 * Everything the browser preview keeps, and how it maps to stored documents.
 *
 * Each document is small and independent (one per idea, objective, run, file, artifact, workflow…),
 * so a change saves only what changed and no document grows past the store's size limit.
 */
import type {
  Agent,
  AgentMessage,
  AgentRun,
  Artifact,
  EventRecord,
  Idea,
  MemoryItem,
  Notification,
  Objective,
  Project,
  TaskNode,
  UserSettings,
  Workflow,
  WorkflowRun,
  WorkflowVersion,
} from "@nexus/schemas";

export interface StoredFile {
  project_id: string;
  path: string; // relative to the project, e.g. "files/notes/a.md"
  content: string;
  modified: number; // seconds since the epoch, like the API
}

export interface StoredVersion {
  version: number;
  content: string;
  created_at: string;
  created_by: string | null;
  note: string;
}

export interface UsageRecord {
  at: string;
  agent: string;
  project_id: string | null;
  model: string;
  input_tokens: number;
  output_tokens: number;
}

export interface PreviewState {
  settings: UserSettings;
  projects: Project[];
  ideas: Idea[];
  notifications: Notification[];
  events: EventRecord[];
  seq: number;
  objectives: Objective[];
  tasks: TaskNode[];
  messages: Record<string, AgentMessage[]>; // by objective id
  runs: AgentRun[];
  steps: Record<string, Record<string, unknown>[]>; // by run id
  agents: Agent[]; // the person's own agents (built-in ones are not stored)
  files: StoredFile[];
  artifacts: Artifact[];
  versions: Record<string, StoredVersion[]>; // by artifact id
  memories: MemoryItem[];
  workflows: Workflow[];
  workflowVersions: Record<string, WorkflowVersion[]>;
  workflowRuns: WorkflowRun[];
  usage: UsageRecord[];
}

export const MAX_EVENTS = 300;
export const MAX_USAGE = 1000;
export const MAX_VERSION_CHARS = 40_000;
export const MAX_VERSIONS_KEPT = 5;

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
    objectives: [],
    tasks: [],
    messages: {},
    runs: [],
    steps: {},
    agents: [],
    files: [],
    artifacts: [],
    versions: {},
    memories: [],
    workflows: [],
    workflowVersions: {},
    workflowRuns: [],
    usage: [],
  };
}

/** A short, stable id for a file path (document ids cannot contain "/"). */
export function pathKey(path: string): string {
  let h = 2166136261;
  for (let i = 0; i < path.length; i++) h = Math.imul(h ^ path.charCodeAt(i), 16777619);
  return (h >>> 0).toString(36);
}

export const fileKey = (f: Pick<StoredFile, "project_id" | "path">): string => `file:${f.project_id}:${pathKey(f.path)}`;

type Body = Record<string, unknown>;

/** The store keeps documents under 256 KiB; leave room for encoding. */
export const MAX_DOC_CHARS = 200_000;
const tooBig = (b: Body) => JSON.stringify(b).length > MAX_DOC_CHARS;

/** The stored body for one document key, small enough to store, or null when what it held is gone. */
export function docBody(s: PreviewState, key: string): Body | null {
  const body = rawBody(s, key);
  if (!body || !tooBig(body)) return body;
  // Keep the newest of whatever grows: versions, messages, steps, history.
  for (const field of ["versions", "messages", "steps", "items"]) {
    const list = body[field];
    if (!Array.isArray(list)) continue;
    let keep = list.length;
    while (keep > 1 && tooBig({ ...body, [field]: list.slice(-keep) })) keep = Math.max(1, Math.floor(keep * 0.75));
    body[field] = list.slice(-keep);
    if (!tooBig(body)) return body;
  }
  return body;
}

function rawBody(s: PreviewState, key: string): Body | null {
  const [kind, id = "", extra = ""] = key.split(":");
  switch (kind) {
    case "settings":
      return { ...s.settings };
    case "projects":
      return { items: s.projects };
    case "notifications":
      return { items: s.notifications };
    case "events":
      return { items: s.events, seq: s.seq };
    case "agents":
      return { items: s.agents };
    case "mem": {
      const item = s.memories.find((m) => m.id === id);
      return item ? { ...item } : null;
    }
    case "usage":
      return { items: s.usage };
    case "idea": {
      const idea = s.ideas.find((i) => i.id === id);
      return idea ? { ...idea } : null;
    }
    case "objective": {
      const objective = s.objectives.find((o) => o.id === id);
      if (!objective) return null;
      return { objective, tasks: s.tasks.filter((t) => t.objective_id === id), messages: s.messages[id] ?? [] };
    }
    case "run": {
      const run = s.runs.find((r) => r.id === id);
      return run ? { run, steps: s.steps[id] ?? [] } : null;
    }
    case "file": {
      const file = s.files.find((f) => f.project_id === id && pathKey(f.path) === extra);
      return file ? { ...file } : null;
    }
    case "artifact": {
      const artifact = s.artifacts.find((a) => a.id === id);
      return artifact ? { artifact, versions: s.versions[id] ?? [] } : null;
    }
    case "workflow": {
      const workflow = s.workflows.find((w) => w.id === id);
      return workflow ? { workflow, versions: s.workflowVersions[id] ?? [] } : null;
    }
    case "wfrun": {
      const run = s.workflowRuns.find((r) => r.id === id);
      return run ? { ...run } : null;
    }
    default:
      return null;
  }
}

const items = <T>(b: Body): T[] => (Array.isArray(b["items"]) ? (b["items"] as T[]) : []);

/** Put one stored document back into the state (when loading). Unknown documents are ignored. */
export function applyDoc(s: PreviewState, key: string, b: Body): void {
  const [kind] = key.split(":");
  switch (kind) {
    case "settings":
      s.settings = { ...s.settings, ...(b as Partial<UserSettings>) };
      return;
    case "projects":
      s.projects = items(b);
      return;
    case "notifications":
      s.notifications = items(b);
      return;
    case "events":
      s.events = items(b);
      s.seq = Number(b["seq"] ?? 0);
      return;
    case "agents":
      s.agents = items(b);
      return;
    case "mem":
      s.memories.push(b as unknown as MemoryItem);
      return;
    case "usage":
      s.usage = items(b);
      return;
    case "idea":
      s.ideas.push(b as unknown as Idea);
      return;
    case "objective": {
      const o = b["objective"] as Objective | undefined;
      if (!o) return;
      s.objectives.push(o);
      s.tasks.push(...((b["tasks"] as TaskNode[] | undefined) ?? []));
      s.messages[o.id] = (b["messages"] as AgentMessage[] | undefined) ?? [];
      return;
    }
    case "run": {
      const r = b["run"] as AgentRun | undefined;
      if (!r) return;
      s.runs.push(r);
      s.steps[r.id] = (b["steps"] as Body[] | undefined) ?? [];
      return;
    }
    case "file":
      s.files.push(b as unknown as StoredFile);
      return;
    case "artifact": {
      const a = b["artifact"] as Artifact | undefined;
      if (!a) return;
      s.artifacts.push(a);
      s.versions[a.id] = (b["versions"] as StoredVersion[] | undefined) ?? [];
      return;
    }
    case "workflow": {
      const w = b["workflow"] as Workflow | undefined;
      if (!w) return;
      s.workflows.push(w);
      s.workflowVersions[w.id] = (b["versions"] as WorkflowVersion[] | undefined) ?? [];
      return;
    }
    case "wfrun":
      s.workflowRuns.push(b as unknown as WorkflowRun);
      return;
  }
}
