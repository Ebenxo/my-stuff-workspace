/**
 * Where the browser preview keeps what the person adds.
 *
 * - On claude.ai (the published preview), each person's data goes to the artifact's `db` store under
 *   their own private path (`data/users/<id>/…`): nobody else, the owner included, can read it.
 *   One document per idea, plus one each for settings, projects, notifications and the history.
 * - Elsewhere (a downloaded copy, a local `vite preview`), this browser's localStorage.
 * - If neither is available, memory only, and the banner says nothing is saved.
 */
import type { DirtyKey, PreviewState } from "./server";

export type StorageKind = "account" | "browser" | "none";

export interface Persistence {
  kind: StorageKind;
  load(): Promise<Partial<PreviewState> | null>;
  save(state: PreviewState, keys: DirtyKey[]): void;
}

// The parts of the claude.ai runtime the preview uses (contract 0.2.x: `claude.use()` only).
interface DocSnap {
  id: string;
  exists: boolean;
  data(): Record<string, unknown> | undefined;
}
interface DocRef {
  set(data: Record<string, unknown>): Promise<void>;
  delete(): Promise<void>;
}
interface CollectionRef {
  doc(id: string): DocRef;
  get(): Promise<{ docs: DocSnap[] }>;
}
interface Db {
  collection(path: string): CollectionRef;
}
interface User {
  id(): Promise<string | null>;
}
interface ClaudeRuntime {
  use(name: "db"): Promise<Db | null>;
  use(name: "user"): Promise<User | null>;
}

const LOCAL_KEY = "nexus-preview-state";

/** Document ids in the person's private collection. Ids allow letters, digits and `_-.~:@+`. */
const docId = (key: DirtyKey): string => key.replace(":", "-");

function accountPersistence(db: Db, uid: string): Persistence {
  const col = db.collection(`data/users/${uid}`);
  // One write at a time per document; a newer value replaces one still waiting.
  const pending = new Map<string, Record<string, unknown> | null>();
  const busy = new Set<string>();
  const flush = async (id: string): Promise<void> => {
    if (busy.has(id)) return;
    busy.add(id);
    try {
      while (pending.has(id)) {
        const value = pending.get(id) ?? null;
        pending.delete(id);
        try {
          if (value === null) await col.doc(id).delete();
          else await col.doc(id).set(value);
        } catch (error) {
          console.error(`NEXUS preview: could not save ${id}`, error);
        }
      }
    } finally {
      busy.delete(id);
    }
  };
  return {
    kind: "account",
    async load() {
      const snap = await col.get();
      if (snap.docs.length === 0) return null;
      const state: Partial<PreviewState> = { ideas: [] };
      for (const d of snap.docs) {
        const body = d.data();
        if (!d.exists || !body) continue;
        if (d.id.startsWith("idea-")) state.ideas?.push(body as never);
        else if (d.id === "settings") state.settings = body as never;
        else if (d.id === "projects") state.projects = (body["items"] ?? []) as never;
        else if (d.id === "notifications") state.notifications = (body["items"] ?? []) as never;
        else if (d.id === "events") {
          state.events = (body["items"] ?? []) as never;
          state.seq = Number(body["seq"] ?? 0);
        }
      }
      return state;
    },
    save(state, keys) {
      for (const key of keys) {
        let value: Record<string, unknown> | null;
        if (key.startsWith("idea:")) {
          const idea = state.ideas.find((i) => i.id === key.slice(5));
          value = idea ? { ...idea } : null; // gone: delete its document
        } else if (key === "settings") value = { ...state.settings };
        else if (key === "events") value = { items: state.events, seq: state.seq };
        else if (key === "projects") value = { items: state.projects };
        else value = { items: state.notifications };
        pending.set(docId(key), value);
        void flush(docId(key));
      }
    },
  };
}

function browserPersistence(): Persistence | null {
  try {
    const probe = "__nexus_probe__";
    localStorage.setItem(probe, "1");
    localStorage.removeItem(probe);
  } catch {
    return null;
  }
  return {
    kind: "browser",
    async load() {
      try {
        const raw = localStorage.getItem(LOCAL_KEY);
        return raw ? (JSON.parse(raw) as Partial<PreviewState>) : null;
      } catch {
        return null;
      }
    },
    save(state) {
      try {
        localStorage.setItem(LOCAL_KEY, JSON.stringify(state));
      } catch (error) {
        console.error("NEXUS preview: could not save to this browser", error);
      }
    },
  };
}

const memoryOnly: Persistence = { kind: "none", load: async () => null, save: () => undefined };

/** Pick the best place to keep the person's data in this view. */
export async function choosePersistence(): Promise<Persistence> {
  const runtime = (window as unknown as { claude?: ClaudeRuntime }).claude;
  if (runtime?.use) {
    try {
      const [db, user] = await Promise.all([runtime.use("db"), runtime.use("user")]);
      const uid = user ? await user.id() : null;
      if (db && uid) return accountPersistence(db, uid);
    } catch (error) {
      console.error("NEXUS preview: account storage is not available", error);
    }
  }
  return browserPersistence() ?? memoryOnly;
}
