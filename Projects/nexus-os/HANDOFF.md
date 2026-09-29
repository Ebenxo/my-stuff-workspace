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
