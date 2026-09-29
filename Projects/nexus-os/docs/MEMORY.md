# NEXUS OS — memory and context

## Four scopes

| Scope | Lifetime | Stored | Written by | Read by |
|---|---|---|---|---|
| **working** | one objective/run | in process (`WorkingMemory`), never persisted | the runner | the same run |
| **conversation** | one conversation | `memory_items` (`scope=conversation`) | Orchestrator/agents via `remember`; user | agents in that conversation |
| **project** | project lifetime | `memory_items` (`scope=project`) | agents via `remember`; user | agents in that project (per `memory_scope`) |
| **global** | until deleted | `memory_items` (`scope=global`) | user; agents *propose* (lands `pending`) | any agent whose `memory_scope` allows global |

`working` memory holds scratch facts, intermediate results and the run's taint set. It is dropped when the run ends; anything worth keeping must be explicitly promoted with `remember`.

## MemoryItem

```
id · scope · project_id · conversation_id · content · summary · importance(0–1) · source{kind, agent_id, task_id, origin}
tags[] · status(active|pending|deleted) · content_hash · access_count · created_at · last_accessed_at · expires_at
+ embedding in memory_embeddings(item_id, embedder, dim, vector)
```

## Write path (never silent, never sensitive)

```
propose(scope, content, source, importance?)
  1. normalise + content_hash
  2. SensitivityGuard.scan(content)  → API keys, private keys, bearer/JWT tokens, passwords in key=value,
        card numbers (Luhn), national-ID-like patterns, cloud credential formats
        hit → REJECT (MEMORY_REJECTED event with the *category*, never the matched text); the agent is told why
  3. exact-duplicate (same scope+hash) → bump importance/last_accessed, no new row
  4. near-duplicate (cosine ≥ 0.92 in the same scope) → merge: keep the newer wording, max importance, union tags
  5. global scope from an agent → status=pending (needs user confirmation), otherwise active
  6. embed + insert + index in search_index → MEMORY_CREATED event (source visible in the Memory browser)
```

Every write is an event and every item is visible, editable and deletable in the Memory browser. Deleting is a soft-delete (`status=deleted`, embedding removed) and a hard purge is available from the UI.

## Retrieval

`MemoryRetriever.search(query, scopes, project_id, k, filters)` returns items with a score breakdown:

```
score = w_sem·cosine(query, item) + w_kw·bm25_norm + w_rec·exp(-age_days/τ) + w_imp·importance + w_task·task_relation
defaults: w_sem .45  w_kw .15  w_rec .15  w_imp .15  w_task .10   τ = 30 days (project), 180 days (global)
```

Semantic similarity uses the configured `Embedder` through the `VectorStore` interface. Keyword scoring uses the FTS index. Accessing an item updates `last_accessed_at`/`access_count` (recency reinforcement).

**Embedder (default):** `HashingEmbedder` — a deterministic, local, dependency-free feature-hashing embedder over normalised word and character n-grams (256 dims). It needs no download and no network, works offline, and gives useful lexical-semantic matching. It is *not* a neural embedder; the `Embedder` interface accepts Ollama / OpenAI-compatible / Gemini embedding endpoints, and changing the embedder triggers a background re-embed (`memory_embeddings.embedder` records which one produced each vector).

**VectorStore:** interface `upsert(id, vector, meta)`, `query(vector, k, filter)`, `delete(id)`. Built: `SQLiteVectorStore` (brute-force cosine over a filtered candidate set; fine to tens of thousands of items). Adding Chroma, Qdrant or pgvector means implementing the interface.

## Compression

`MemoryCompressor` runs as a background job per project: candidates are low-importance, old, rarely accessed items that share tags/similarity. With a provider available it asks a cheap model for a structured summary (`{summary, merged_ids}`); with none it falls back to a deterministic extractive summary. The originals are soft-deleted only after the summary item is written (and the operation is an event, reversible from the Memory browser for 30 days).

## Importance

Initial importance comes from the source: user-authored 0.8, decision/preference 0.7, agent-proposed 0.5, auto-summaries 0.4; explicit `importance` from the proposer is clamped to ±0.2 of that band so an agent cannot self-promote its memories.

## ContextBuilder

```
ContextBuilder.build(ctx: ContextRequest) -> BuiltContext
  ctx: agent, objective, task, conversation_id, project_id, budget_tokens, recent_messages, tool_results, upstream_outputs
```

Steps: (1) collect candidate `ContextSegment`s (system, agent, objective, task, project facts, conversation window, memory recalls, retrieved file excerpts, upstream outputs, recent tool results); (2) score each by semantic relevance to the task, recency, importance, and task relationship (upstream outputs and files named in the task rank highest); (3) reserve mandatory segments (system, agent, objective, task) first; (4) fill the remaining budget greedily by score/token, truncating a segment at a sentence boundary rather than dropping it when it is the only high-value item; (5) render with trust fences (see SECURITY.md §7); (6) return the rendered messages plus a `ContextReport` (what was included, dropped, and why, with token counts) that is shown in the UI's **Context** panel. Token counts use the provider's `count_tokens` where available and a conservative `chars/3.5` estimate otherwise, with a 10 % safety margin.

## What the user can do

View, search, edit, pin (importance = 1), confirm/reject `pending`, delete, and purge memories; filter by scope/tag/source; see which memories were recalled into which run (the `ContextReport` is stored with the run). Nothing is stored about the user outside these visible items.
