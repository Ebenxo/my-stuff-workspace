# NEXUS OS — memory and context

_Built in Phase 7. Code: `app/memory/` (service, sensitivity guard, embedder, scoring, compression), `app/agents/context.py` (ContextBuilder), `app/repositories/memory_store.py`, `app/repositories/search_index.py`, `app/services/universal_search.py`._

## Scopes

| Scope | Lifetime | Stored | Written by | Read by |
|---|---|---|---|---|
| **working** | one run | the run's checkpoint (its steps and results) | the runner | the same run, including after a resume |
| **project** | project lifetime | `memory_items` (`scope=project`) | the person; agents via `remember`; objective suggestions (after the person keeps them) | agents in that project whose `memory_scope.read` includes `project` |
| **global** | until deleted | `memory_items` (`scope=global`) | the person; agents *propose* (lands `pending`) | agents in every project whose `memory_scope.read` includes `global` |
| **conversation** | one conversation | `memory_items` (`scope=conversation`) | not used yet (no conversation UI drives agents) | — |

Anything worth keeping beyond a run must be written with `remember` (or by the person). Nothing is remembered silently: an objective's outcome is only a *suggestion* until the person keeps it.

## MemoryItem

```
id · scope · project_id · content · importance(0–1, pinned = 1) · tags[] · status(active|pending|deleted)
source{kind: user|agent|objective|summary, agent, run_id, task_id, objective_id, tainted, private}
content_hash · access_count · last_accessed_at · merged_into (compression) · created_at · updated_at
+ memory_embeddings(item_id, embedder, dim, vector)
```

## Write path (never silent, never sensitive)

```
propose(content, scope, project_id, source, tags?, importance?)
  1. normalise whitespace; project scope needs a project; global drops the project id
  2. SensitivityGuard.scan → API keys, private keys, tokens (bearer, JWT, GitHub, Slack), credential
     assignments, cloud credentials, payment card numbers (Luhn, major-network prefix), national identity
     numbers (US SSN, UK NI), bank account numbers (IBAN mod-97)
       hit → REFUSED. MEMORY_REJECTED records the *category* only; the matched text is never stored or logged
  3. exact duplicate (same scope, project and content, case-insensitive) → reuse: max importance, union of tags
  4. near duplicate (cosine ≥ 0.92, same scope, project and privacy) → merge: newer wording, max importance,
     union of tags. Exception: an agent never rewrites the person's own words (its note is dropped as a duplicate)
  5. status: pending for agent-proposed global memory and for objective suggestions; otherwise active
  6. importance from the source band (below), embed, store, index for search → MEMORY_CREATED (with a preview)
```

Every item is visible, editable, pinnable and deletable in Memory. Deleting is soft (`status=deleted`, vector and search entry removed) and can be undone; **Erase for good** purges the row. Every change is an event.

**Importance bands.** Written by the person 0.8, agent 0.5, objective outcome 0.4, compression summary 0.4. An agent's own `importance` is clamped to ±0.2 of its band, and a note written after reading untrusted content is capped at 0.4. Pinning sets 1.0 (unpinning returns to the band).

**Taint.** A note written by a run that had read untrusted content is marked `source.tainted` and shown with an "After outside content" flag. A later run that is given it, or recalls it with `search_memory`, is tainted too (`memory:<id>` in its taint set), with the usual consequences (SECURITY.md §6).

**Privacy.** A note written during a "keep on this device" run is marked `source.private` and is only ever recalled into other private runs, so it never reaches a cloud model. Private and shareable notes never merge.

## Retrieval

`MemoryService.search(query, scopes, project_id, k, objective_id)` ranks live (`active`) items and returns each with its score breakdown:

```
score = .45·semantic + .15·keyword + .15·recency + .15·importance + .10·task
semantic   cosine(query vector, item vector)
keyword    BM25 over the candidate set, divided by the best in the set (0–1)
recency    exp(-age/τ), age since last use or change; τ = 30 days (project), 180 (global)
importance 0–1 (above)
task       1 if the item came from the same objective; 0.5 if its tags name words in the query
```

An item must be *about* the query (semantic ≥ 0.12 or any keyword match): importance and recency rank relevant items but never make an unrelated item relevant. Candidates are the live items in scope (up to 2,000, most important and recent first); similarity is computed in process. When an agent is given or recalls an item, its `access_count` and `last_accessed_at` are updated (recency reinforcement). The person browsing or testing recall in the UI does not count as use.

**Embedder.** `HashingEmbedder` (`hashing-v1-256`): deterministic, local, dependency-free signed feature hashing over normalised words (stopwords removed, light plural/verb folding), word pairs and character trigrams, 256 dimensions, L2-normalised. It needs no download or network. It is lexical, not neural: "invoice", "invoices" and "invoicing" are close; "car" and "automobile" are not. Each vector records its embedder; at startup, items with no vector or one from another embedder are re-embedded, so a neural embedder can be swapped in behind the `Embedder` protocol. Not extracted yet: a `VectorStore` interface for Chroma, Qdrant or pgvector (vectors live in `memory_embeddings`).

## Compression

**Tidy old notes** (per project) folds old, low-value notes that belong together into one summary: candidates are active project notes older than 30 days with importance ≤ 0.5 and used at most once (the person's own notes, at 0.8, are never compressed). Groups form from notes similar to any member (cosine ≥ 0.28, measured: related notes score about 0.3 to 0.4 with this embedder, unrelated ones below 0.2) or sharing a tag; only groups of three or more are compressed. The summary keeps the group's most central sentences in their original order (deterministic, no model call). The originals are soft-deleted only after the summary exists, keep a link to it, and **Restore the originals** undoes the whole step. Each compression is a `MEMORY_COMPRESSED` event.

## ContextBuilder

Runs once when a run is created (`AgentRunner.create`); the result is stored with the run's request, so a resumed run sees exactly the same context.

1. Candidates, in priority order: the caller's blocks (for an orchestrated task: upstream outputs and reviews), the project's pinned memories (standing facts), then memories recalled for the run's title and task (top 6).
2. The budget (12,000 tokens by default; 3.5 characters per token plus a 10 % margin and fence overhead) is filled in that order, best score first. A caller's block that does not fit is cut at a sentence boundary with a note of what was omitted; a memory that does not fit is left out.
3. Everything is rendered by the PromptBuilder inside trust fences with a random nonce; fence-like text inside content is neutralised, so a remembered note cannot close its fence or pose as instructions.
4. A `ContextReport` (each item: given, shortened or left out; why; score; tokens; budget used) is stored with the run and shown on the run page under **What it was given**.

Files are not pre-loaded: agents read them through tools, so every read is logged and taints the run when the content is untrusted.

## Suggestions after an objective

When an objective completes (or partly completes), NEXUS proposes a project memory of its outcome ("Objective … finished (PASS): <Verifier summary>. Deliverables: …"). It is `pending`: the objective page asks **Remember this for next time?** (Remember / Edit first / No thanks), and it also waits under Memory → Suggestions. An outcome that is already remembered, or already waiting as a suggestion, is not suggested again.

## Universal search

`GET /api/search` searches projects (name, description), objectives (text and result summary), text deliverables (name and content, first 200 KB read, 20,000 characters indexed) and memory, in one FTS5 index (`search_index`, bm25 with title matches weighted 5×, highlighted snippets). Free text is turned into quoted terms joined by AND with a prefix match on the last word, so FTS syntax typed by a person is always literal. If a SQLite build lacks FTS5 the migration creates a plain table and search falls back to LIKE on every word. The index follows the event log (an in-process listener re-indexes a project, objective or deliverable whenever an event says it changed; memory is indexed by the MemoryService) and is rebuilt at startup when empty. Project files are not indexed (agents search them with `search_files`).

## What the person can do

View, filter (scope, source, text, tag), rank as agents would (with the score breakdown), add, edit, pin, keep or dismiss suggestions, delete and restore, erase for good, and tidy old notes (reversible), from the Memory page or a project's Memory tab; see what each run was given on the run page; search everything from the top bar. Nothing is stored about the person outside these visible items.
