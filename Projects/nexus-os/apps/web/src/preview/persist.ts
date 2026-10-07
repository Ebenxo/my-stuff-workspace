/**
 * Where the browser preview keeps what the person adds.
 *
 * - On claude.ai (the published preview), each person's data goes to the artifact's `db` store under
 *   their own private path (`data/users/<id>/…`): nobody else, the owner included, can read it.
 *   One small document per thing (see `state.ts`), so a change writes only what changed.
 * - Elsewhere (a downloaded copy, a local `vite preview`), this browser's localStorage.
 * - If neither is available, memory only, and the banner says nothing is saved.
 */
export type StorageKind = "account" | "browser" | "none";
export type Body = Record<string, unknown>;

export interface Persistence {
  kind: StorageKind;
  /** Every saved document by key, or null when nothing was saved yet. */
  load(): Promise<Map<string, Body> | null>;
  /** Write these documents; null deletes one. */
  save(docs: [string, Body | null][]): void;
}

// The parts of the claude.ai runtime the preview uses (contract 0.2.x: `claude.use()` only).
interface DocSnap {
  id: string;
  exists: boolean;
  data(): Body | undefined;
}
interface DocRef {
  set(data: Body): Promise<void>;
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
export interface ClaudeRuntime {
  use(name: string): Promise<unknown>;
}

const LOCAL_KEY = "nexus-preview-docs";
const OLD_LOCAL_KEY = "nexus-preview-state"; // the first preview kept everything in one value

/**
 * Document ids allow letters, digits and `_-.~:@+`. The first ":" becomes "-" (as in the first
 * preview's `idea-<id>` documents, which keep loading).
 */
const docId = (key: string): string => key.replace(":", "-");
const KINDS = /^(idea|objective|run|file|artifact|workflow|wfrun|mem)-/;
const keyOf = (id: string): string => (KINDS.test(id) ? id.replace("-", ":") : id);

function accountPersistence(db: Db, uid: string): Persistence {
  const col = db.collection(`data/users/${uid}`);
  // One write at a time per document; a newer value replaces one still waiting.
  const pending = new Map<string, Body | null>();
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
      const docs = new Map<string, Body>();
      for (const d of snap.docs) {
        const body = d.exists ? d.data() : undefined;
        if (body) docs.set(keyOf(d.id), body);
      }
      return docs.size ? docs : null;
    },
    save(docs) {
      for (const [key, value] of docs) {
        pending.set(docId(key), value);
        void flush(docId(key));
      }
    },
  };
}

/** The first preview's single saved value, as documents. */
function fromOldState(old: Body): Map<string, Body> {
  const docs = new Map<string, Body>();
  if (old["settings"]) docs.set("settings", old["settings"] as Body);
  if (Array.isArray(old["projects"])) docs.set("projects", { items: old["projects"] });
  if (Array.isArray(old["notifications"])) docs.set("notifications", { items: old["notifications"] });
  if (Array.isArray(old["events"])) docs.set("events", { items: old["events"], seq: old["seq"] ?? 0 });
  for (const idea of Array.isArray(old["ideas"]) ? (old["ideas"] as Body[]) : []) docs.set(`idea:${String(idea["id"])}`, idea);
  return docs;
}

function browserPersistence(): Persistence | null {
  try {
    const probe = "__nexus_probe__";
    localStorage.setItem(probe, "1");
    localStorage.removeItem(probe);
  } catch {
    return null;
  }
  let all: Record<string, Body> = {};
  return {
    kind: "browser",
    async load() {
      try {
        const raw = localStorage.getItem(LOCAL_KEY);
        if (raw) {
          all = JSON.parse(raw) as Record<string, Body>;
          return new Map(Object.entries(all));
        }
        const old = localStorage.getItem(OLD_LOCAL_KEY);
        if (!old) return null;
        const docs = fromOldState(JSON.parse(old) as Body);
        all = Object.fromEntries(docs);
        localStorage.setItem(LOCAL_KEY, JSON.stringify(all));
        localStorage.removeItem(OLD_LOCAL_KEY);
        return docs;
      } catch {
        return null;
      }
    },
    save(docs) {
      for (const [key, value] of docs) {
        if (value === null) delete all[key];
        else all[key] = value;
      }
      try {
        localStorage.setItem(LOCAL_KEY, JSON.stringify(all));
      } catch (error) {
        console.error("NEXUS preview: could not save to this browser", error);
      }
    },
  };
}

const memoryOnly: Persistence = { kind: "none", load: async () => null, save: () => undefined };

/** Pick the best place to keep the person's data in this view. */
export async function choosePersistence(runtime: ClaudeRuntime | undefined): Promise<Persistence> {
  if (runtime?.use) {
    try {
      const [db, user] = (await Promise.all([runtime.use("db"), runtime.use("user")])) as [Db | null, User | null];
      const uid = user ? await user.id() : null;
      if (db && uid) return accountPersistence(db, uid);
    } catch (error) {
      console.error("NEXUS preview: account storage is not available", error);
    }
  }
  return browserPersistence() ?? memoryOnly;
}
