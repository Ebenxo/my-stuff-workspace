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

`scripts/dev.py` stores data in `data/dev/` (gitignored), creates a per-launch API token, and hands it to the Vite dev proxy so it never ships in the browser bundle. Works on Windows, macOS and Linux. Only one API can use a data folder at a time; a second copy needs its own folder and port, e.g. `NEXUS_PORT=8766 python scripts/dev.py --api-only --home data/dev2`.

## Try the demo

On the Command Center press **Try the demo**. It creates a demo project with three notes about fictional products (every file is labelled *DEMO DATA*) and the objective *Research three AI coding assistants and create a comparison report*. The agents' answers come from a scripted demo model, so it works without a provider and nothing leaves your machine; everything else (planning, validation, the task graph, tools, reviews, verification, deliverables, events) is the real system. Review the plan, press **Run plan**, and watch the Researcher, Writer, Critic and Verifier work.

## Give NEXUS an objective

1. Settings → AI providers: connect a provider (a local model through Ollama or LM Studio keeps everything on your machine).
2. Projects → New project, then put a file or two into its **Files** tab.
3. On the Command Center, describe what you want done and press **Start**. The Planner proposes tasks for the team; you can edit the plan, run it, or run only the safe steps. Anything risky (deleting, running commands, sending data out) waits on an approval card until you decide. The Verifier checks the result against the plan's completion criteria, and deliverables land in the project's **Deliverables** with version history.

For a single focused job you can also run one agent directly from **Agents**.

## Memory and search

NEXUS remembers what you (and, with your say-so, its agents) decide is worth keeping: facts, decisions and preferences, per project or across all projects. Before each run the relevant memories are given to the agent as clearly marked background; the run page shows exactly what it was given and why. Everything remembered is visible and editable under **Memory**, suggestions wait for you, and passwords, keys and personal identifiers are refused outright. The search box in the top bar finds projects, objectives, deliverables and memories. Details: [`docs/MEMORY.md`](docs/MEMORY.md).

## Workflows and schedules

For work you repeat, build a **workflow** under **Workflows** (or a project's Workflows tab): a chain of steps drawn top to bottom — an agent task, a tool, a yes/no condition, an approval that waits for you, computed values, a delay, a loop over a list, another workflow — with inputs you fill in when it runs. Select a step and click a step type to add the next one; `{{ inputs.topic }}`-style templates pass values along. The editor checks the workflow as you build it and every save is a version. Give it a **schedule** (cron, with presets and a plain-words preview) and it runs while NEXUS is open; scheduled runs never approve anything risky on their own — they wait for you under *Needs you*.

## Quality gates

```bash
python scripts/check.py          # lint, strict types, import contracts, tests, API-type drift, build
python scripts/check.py --fast   # skip the production build and cargo tests
python scripts/gen_openapi.py    # regenerate TypeScript API types after changing the backend
```

## Security posture in one paragraph

The API listens on loopback only, requires a bearer token on every call (except a minimal liveness ping), rejects foreign `Host` and `Origin` headers, and rate-limits requests. Secrets live in the OS keychain (or a private file, reported as *degraded* in System Health) and are never returned by the API or written to logs. Agents can only *propose* actions; a policy engine that no text can influence decides what runs, and the event log is hash-chained so tampering is detectable. Details and limits: [`docs/SECURITY.md`](docs/SECURITY.md).
