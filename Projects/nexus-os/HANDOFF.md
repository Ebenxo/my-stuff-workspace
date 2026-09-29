# HANDOFF — nexus-os

Shared log between Claude Code and Codex (neither shares chat history). Read `docs/BUILD_STATE.md` for the live engineering state and `docs/BRIEF.md` for the decisions and acceptance criteria. This file records session-level decisions, what changed, what was verified, and what is next.

## 2026-09-29 — Phase 0 — Claude Code

**Request:** "improve the prompt and execute" — the owner supplied a 60-section spec for NEXUS OS, a local-first agentic operating system.
**Decided:**
- Rewrote the prompt into `docs/BRIEF.md` (priorities, 12 resolved contradictions, acceptance criteria mapped to the 20-point MVP definition).
- Project lives at `Projects/nexus-os/` (workspace rule). It is a code project, so the design `Drafts/Final` split does not apply; state is tracked in this file and `docs/BUILD_STATE.md`.
- Nothing in `FormAndFlow/`, `Business-Ops/`, or other projects is touched.
**Changed:** new folder `Projects/nexus-os/` only (docs + `.gitignore`).
**Verified:** docs cross-read for consistency (tool names, risk levels, table names).
**Not verified / caveats:** no code yet. Environment limits (no live API keys, no webkit for Tauri) are recorded in `docs/BUILD_STATE.md`.
**Next:** Phase 1 foundation.

## 2026-09-29 — Phase 1 (foundation) — Claude Code

**Built:** Python API (FastAPI, SQLite + Alembic, hash-chained event log with SSE, auth/Host/Origin/rate-limit middleware, secret store), React web app (shell, Command Center, Projects, Settings/System Health), design tokens, Rust `nexus-sidecar` crate, Tauri scaffold, dev/check/gen scripts.
**Verified:** `python scripts/check.py` all green (74 pytest, 26 vitest, 8 cargo tests, ruff, mypy strict, import contracts, eslint, tsc, web build, API-type drift). App run for real via `scripts/dev.py` and driven with Playwright: create project, terminal commands, audit verification; screenshots at 1440px and 390px, no overflow, no console errors; contrast ratios computed.
**Not verified:** Tauri glue never compiled (no webkit here); keychain path; production API packaging.
**Decisions:** see `docs/BUILD_STATE.md` ("Architecture decisions", "Bugs found").
**Next:** Phase 2, providers.

## 2026-09-29 — Phase 2 (AI providers) — Claude Code

**Built:** provider abstraction + Anthropic/OpenAI-compatible/Ollama/Gemini adapters, structured output with repair, model catalog + router (privacy-safe), gateway (retry/backoff/fallback), usage + budgets, provider CRUD with write-only keys, Settings → AI providers and Usage & budgets pages.
**Verified:** `python scripts/check.py` green (220 pytest, 39 vitest, 8 cargo). Real-socket tests (chunked SSE, auth, redirect key-replay, proxy bypass). Full stack driven with Playwright against a local fake LM Studio and the real Anthropic endpoint (401 for a fake key, as expected); key absent from DOM/localStorage; no overflow at 390px.
**Bugs found by the live check:** LM Studio default URL fell through to OpenAI's; see `docs/BUILD_STATE.md`.
**Not verified:** successful live generation on any cloud provider (no valid keys); Gemini native schema per model.
**Owner action (optional):** to verify live, add a real key in Settings → AI providers and press Test connection.
**Next:** Phases 3–4, agent runtime + tools + permissions.

## 2026-09-29 — Phases 3–4 (agent runtime, tools, permissions) — Claude Code

**Built:** ten built-in agents; the agent loop with every guard (steps, tool calls, tokens, working time excluding waits for a person, loop detection), checkpoints, resume, cancel and startup recovery; 22 tools behind one executor (policy engine, approvals once/session/deny/edit, taint tracking, injection flags, sandbox, SSRF guard, path guard, versioned artifacts); private runs that cannot reach off the machine; APIs for agents, runs, approvals, tools, tool calls, artifacts and project files; UI for the team, live runs, approval cards, project files/deliverables/runs/tool activity, and tool switches.
**Verified:** `python scripts/check.py` green (714 pytest, 83 vitest, 8 cargo, ruff, mypy strict, 3 import contracts, eslint, tsc, build, API-type drift). Real API + web app driven with Playwright against a local stand-in model: an agent saved a deliverable; a delete waited for approval (file present before, gone after); an agent's question was answered; no console errors; no overflow at 390 px; screenshots checked by eye.
**Bugs the live check found (fixed, with tests):** a second API on the same data folder interrupted the first's live runs (now an OS lock on the folder); trailing-slash redirects bypassed the dev proxy's token (redirects disabled); `scripts/dev.py` orphaned its children and could report "ready" against an old server; duplicated lines in the Activity panel. Also corrected two docs that claimed things that were not true (web search blocked for private runs — now implemented; dependency audits in `check.py` — not yet, scheduled for Phase 10).
**Not verified:** agents with a real model (only scripted ones here); Windows sandbox path; Tauri build (no webkit here).
**Next:** Phases 5–6, planner, orchestrator, task graph, multi-agent review and verification, demo project.

## 2026-09-29 — Phases 5–6 (objectives, orchestrator, multi-agent) — Claude Code

**Built:** objectives end to end: Planner → validator (one repair round) → strategy → tasks (migration `0003`); plan review and editing; an orchestrator running ready tasks in parallel (max 3) through the agent runner; Critic review → revision loop (2 rounds); Verifier with evidence per criterion and one follow-up re-plan; deterministic recovery (retry / resume / skip / block / fail) with per-task retry, skip and answer; agent hand-offs as events; the labelled demo ("Try the demo", scripted model, fictional products). UI: Command Center objective box and list, objective page (plan review and editor, live task graph with list view, task details, approvals, verified result, hand-offs, activity), project Objectives tab.
**Verified:** `python scripts/check.py` green (785 pytest, 102 vitest, 8 cargo, ruff, mypy strict, import contracts, eslint, tsc, build, API-type drift). Real API + web app driven with Playwright: the demo planned, ran through research, writing, a Critic-requested revision, a second review and verification to PASS (4/4 criteria), and the report opened from the result; no console errors or failed requests; no overflow at 390 px; screenshots checked by eye.
**Bugs the live check found (fixed):** the Planner's full internal prompt showed in the Activity panel (runs now carry a short title); the task graph did not re-fit as reviews and revisions were added or when the details panel closed; task rows clipped on phones; after the demo, its scripted provider counted as a connected provider. Earlier backend bugs are listed in `docs/BUILD_STATE.md`.
**Not verified:** planning, reviewing and verifying with a real model (scripted only here); model/tool switching and delegation in recovery are not built.
**Next:** Phase 7, memory and the context engine.

## 2026-09-29 — Phase 7 (memory, context engine, search) — Claude Code

**Built:** memory (migration `0004`) with a sensitivity guard that refuses secrets and personal identifiers, duplicate reuse and merging, suggestions the person confirms, importance bands, delete/restore/erase, and reversible compression; ranked recall with a visible score breakdown and a local hashing embedder; a ContextBuilder that gives each run its inputs, pinned facts and relevant memories within a budget, stored with the run and shown on the run page; `search_memory`/`remember` tools on the built-in agents; taint and privacy carried through memory; universal search (FTS5, LIKE fallback) fed by the event log. UI: Memory page and project tab, objective "Remember this for next time?", run "What it was given", top-bar search and Search page.
**Verified:** `python scripts/check.py` green (839 pytest, 115 vitest, 8 cargo, ruff, mypy strict, import contracts, eslint, tsc, build, API-type drift). Live with Playwright on the real API and web app: demo → suggestion kept → pinned memory added, a key refused by category → a second demo gave all 6 runs relevant memory → search found the report; no console errors; no overflow at 390 px.
**Caught while building:** memories from private runs could have reached cloud runs through recall (now impossible, tested); a placeholder number was refused as a card; the compression threshold was tuned from measured similarities; tools could not pass taint on (now they can).
**Not verified:** recall quality with real models; the embedder is lexical, not neural.
**Next:** Phases 8–9, workflows, scheduler, MCP.

## 2026-09-29 — Phase 8 (workflows, scheduler) — Claude Code

**Built:** versioned workflow definitions (migration `0005`) with ten step types, typed inputs and validation in plain words; a safe expression language (allow-listed `ast` interpreter) for `{{ templates }}` and conditions; an engine that runs steps in parallel (max 3), follows yes/no paths, parks on approvals, resumes after a restart, cancels, retries failed steps and nests sub-workflows (3 deep); agent and tool steps go through the existing runner and executor, and scheduled runs never auto-approve HIGH or VERY_HIGH actions; a cron scheduler with time zones, previews in words, catch-up once and skip-while-running. UI: Workflows page and project tab, a top-to-bottom React Flow editor (new steps attach to the selected one; handles can be dragged), step inspector, live validation, versions, run dialog, run page with approvals, schedule panel.
**Verified:** `python scripts/check.py` green (912 pytest, 126 vitest, 8 cargo, ruff, mypy strict, import contracts, eslint, tsc, build, API-type drift). Live with Playwright on the real API and web app: built Start → Approval → Tool → Output (+ a dragged Delay), saved as v2, ran it: it waited for approval with the file absent, then completed and wrote the file; a bad cron was explained; a weekday schedule created; no console errors besides the deliberate 422s; no overflow at 390 px.
**Bugs found (fixed, with tests):** a decision arriving at the wrong moment was not seen until the next event; cancel left a tool step's approval pending; shutdown marked running steps cancelled instead of interrupted; a deleted workflow's schedule lost its reason; live: tiny handles and a horizontal layout made building workflows hard (now vertical, larger handles, auto-connect).
**Not verified:** workflow agent steps with a real model (scripted only); schedules only fire while NEXUS runs; no webhook/file triggers, canvas undo, or export yet.
**Next:** Phase 9, MCP servers.
