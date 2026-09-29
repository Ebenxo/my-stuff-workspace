# NEXUS OS

A local-first **agentic operating system**: give it an objective, and a Planner turns it into a task graph, an Orchestrator delegates to specialist agents, every action passes through a permission pipeline, sensitive steps wait for your approval, a Critic and Verifier check the work, and everything is saved as versioned artifacts with a complete, tamper-evident activity log.

> **Build status:** in active construction, phase by phase. See [`docs/BUILD_STATE.md`](docs/BUILD_STATE.md) for exactly what works today, what is verified, and what is not.

## Documentation

| Doc | What it covers |
|---|---|
| [`docs/BRIEF.md`](docs/BRIEF.md) | The improved product brief: priorities, resolved contradictions, acceptance criteria |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Modules, data flow, action pipeline, execution lifecycle, extension points |
| [`docs/DATABASE.md`](docs/DATABASE.md) | Schema and migration plan |
| [`docs/AGENTS.md`](docs/AGENTS.md) | Agent definitions, built-in team, structured contracts, review and recovery |
| [`docs/TOOLS.md`](docs/TOOLS.md) | Tool interface, built-in tools, risk levels, sandbox |
| [`docs/MEMORY.md`](docs/MEMORY.md) | Memory scopes, retrieval, context engine |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Threat model, permission engine, prompt-injection defences, known limits |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Phases and exit criteria |

## Layout

```
apps/web        React + Vite + TypeScript + Tailwind UI (the only UI codebase)
apps/desktop    Tauri shell + tested sidecar supervisor (see its README for status)
services/api    Python (FastAPI) API and agent runtime
packages/ui     Design tokens and primitives
packages/shared Typed API client, SSE client with resume, formatters
packages/schemas TypeScript types generated from the API's OpenAPI document
```

## Run it (development)

Prerequisites: Python 3.11+, [`uv`](https://docs.astral.sh/uv/), Node 20+, [`pnpm`](https://pnpm.io/).

```bash
pnpm install
(cd services/api && uv sync)
python scripts/dev.py          # API on http://127.0.0.1:8765, web on http://localhost:5173
```

`scripts/dev.py` stores data in `data/dev/` (gitignored), creates a per-launch API token, and hands it to the Vite dev proxy so it never ships in the browser bundle. Works on Windows, macOS and Linux.

## Quality gates

```bash
python scripts/check.py          # lint, strict types, import contracts, tests, API-type drift, build
python scripts/check.py --fast   # skip the production build and cargo tests
python scripts/gen_openapi.py    # regenerate TypeScript API types after changing the backend
```

## Security posture in one paragraph

The API listens on loopback only, requires a bearer token on every call (except a minimal liveness ping), rejects foreign `Host` and `Origin` headers, and rate-limits requests. Secrets live in the OS keychain (or a private file, reported as *degraded* in System Health) and are never returned by the API or written to logs. Agents can only *propose* actions; a policy engine that no text can influence decides what runs, and the event log is hash-chained so tampering is detectable. Details and limits: [`docs/SECURITY.md`](docs/SECURITY.md).
