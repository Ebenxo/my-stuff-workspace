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

Prerequisites: Python 3.11+, [`uv`](https://docs.astral.sh/uv/), Node 20+, [`pnpm`](https://pnpm.io/) (after installing Node, `corepack enable` provides it).

**Windows:** double-click **`start.cmd`** in this folder. **macOS / Linux:** run `python3 scripts/dev.py`.

Either way it checks the tools above and says how to get any that are missing, installs the project's own packages the first time (a few minutes), starts the API and the web app, waits until they answer, and opens **http://localhost:5173** in your browser. Keep that window open while you use NEXUS; press Ctrl+C or close it to stop. (`--no-browser` skips opening the browser; the manual steps are `pnpm install`, `cd services/api && uv sync`, then `python scripts/dev.py`.)

**"This site can't be reached"?** NEXUS only runs on your own computer, so:
- open the address **on the computer where `start.cmd` (or `scripts/dev.py`) is running**: a phone or another computer cannot reach it;
- wait for the window to say *NEXUS is ready* (the first start installs packages first);
- keep that window open (closing it stops NEXUS);
- if the window shows an error instead, it says what is missing or what failed.

`scripts/dev.py` stores data in `data/dev/` (gitignored), creates a per-launch API token, and hands it to the Vite dev proxy so it never ships in the browser bundle. Works on Windows, macOS and Linux. Only one API can use a data folder at a time; a second copy needs its own folder and port, e.g. `NEXUS_PORT=8766 python scripts/dev.py --api-only --home data/dev2`.

## First run

The first time NEXUS opens it asks four things: what to call you, how careful agents should be (cautious, balanced or permissive; deleting files, running commands and sending data out always ask), where project files live, and which model to use (or none yet). Then you can try the demo or go straight to the Command Center. **Skip setup** keeps the defaults.

## Getting around

Press **Ctrl K** (⌘K on a Mac) anywhere for the command palette: type part of a page, an action ("new workflow", "add an MCP server", "try the demo") or a project, or anything to search for. **?** lists every shortcut: **/** searches, **G** then a letter goes to a page (C Command Center, T Timeline, P Projects, A Agents, W Workflows, R Approvals, M Memory, I Ideas & notes, S Settings), **Ctrl J** shows the bottom panel with events and the NEXUS command line (`help`, `status`, `approvals`, `open <page>`, `search <words>`, `verify`).

## Timeline: everything in one place

**Timeline** (in the sidebar, or **G T**) shows what needs you (approvals, plans waiting for review, agents with a question, workflows at an approval step, overdue to-dos), what is happening now (objectives, agents and workflows at work), what is coming up (scheduled workflow runs and to-dos by due time), what you pinned, and below it the full history, newest first and grouped by day. Every entry links to the thing it is about; **Show every step** adds the fine-grained agent and tool steps; **Load older** goes back as far as the log goes; a project filter narrows it all to one project. It updates live. The Command Center shows the first few items in *Needs you & coming up*.

## Ideas, notes and to-dos

**Ideas & notes** (or **G I**) keeps the small things: ideas, notes and to-dos, each optionally in a project, pinned, or given a due time (with quick choices such as *Tomorrow morning*). When a to-do comes due, NEXUS sends one notification and puts it under *Needs you*; moving the due time sets a new reminder. Mark things done, edit them in place, search them, and start any idea as an objective with one click (you still review the plan first). The Command Center has a one-line *Jot something down* box: type, press Enter; start with `todo:` or `note:` to choose the kind. Ideas are part of the top-bar search.

## Try the demo

On the Command Center press **Try the demo**. It creates a demo project with three notes about fictional products (every file is labelled *DEMO DATA*) and the objective *Research three AI coding assistants and create a comparison report*. The agents' answers come from a scripted demo model, so it works without a provider and nothing leaves your machine; everything else (planning, validation, the task graph, tools, reviews, verification, deliverables, events) is the real system. Review the plan, press **Run plan**, and watch the Researcher, Writer, Critic and Verifier work.

## Give NEXUS an objective

1. Settings → AI providers: connect a provider (a local model through Ollama or LM Studio keeps everything on your machine).
2. Projects → New project, then put a file or two into its **Files** tab.
3. On the Command Center, describe what you want done and press **Start**. The Planner proposes tasks for the team; you can edit the plan, run it, or run only the safe steps. Anything risky (deleting, running commands, sending data out) waits on an approval card until you decide. The Verifier checks the result against the plan's completion criteria, and deliverables land in the project's **Deliverables** with version history.

For a single focused job you can also run one agent directly from **Agents**.

## Memory and search

NEXUS remembers what you (and, with your say-so, its agents) decide is worth keeping: facts, decisions and preferences, per project or across all projects. Before each run the relevant memories are given to the agent as clearly marked background; the run page shows exactly what it was given and why. Everything remembered is visible and editable under **Memory**, suggestions wait for you, and passwords, keys and personal identifiers are refused outright. The search box in the top bar finds projects, objectives, deliverables, memories and ideas. Details: [`docs/MEMORY.md`](docs/MEMORY.md).

## Workflows and schedules

For work you repeat, build a **workflow** under **Workflows** (or a project's Workflows tab): a chain of steps drawn top to bottom — an agent task, a tool, a yes/no condition, an approval that waits for you, computed values, a delay, a loop over a list, another workflow — with inputs you fill in when it runs. Select a step and click a step type to add the next one; `{{ inputs.topic }}`-style templates pass values along. The editor checks the workflow as you build it and every save is a version. Give it a **schedule** (cron, with presets and a plain-words preview) and it runs while NEXUS is open; scheduled runs never approve anything risky on their own — they wait for you under *Needs you*.

## Connect other tools (MCP)

Settings → **Integrations** connects [Model Context Protocol](https://modelcontextprotocol.io) servers: a program on this computer (for example one started with `npx` or `uvx`) or a server's web address. Tokens go under *secret values*: they are kept in the secret store and never shown again. A server's tools appear under Tools & approvals as `mcp__<server>__<tool>`, at high risk unless you choose otherwise; an agent can use them once you add them to its tools, and every call goes through the same checks and approvals as any other risky action. Their results count as outside content, they are never available to runs kept on this device, and a tool whose description changes or reads like instructions to an AI is switched off until you look at it. Servers run with your own permissions, so only add ones you trust. Details: [`docs/TOOLS.md`](docs/TOOLS.md) and [`docs/SECURITY.md`](docs/SECURITY.md).

## Quality gates

```bash
python scripts/check.py            # lint, strict types, import contracts, tests, API-type drift, build,
                                   # dependency audits and the end-to-end walkthrough in a browser
python scripts/check.py --fast     # skip the build, cargo tests, audits and the end-to-end run
python scripts/check.py --offline  # everything except the dependency audits (they need the internet)
python scripts/e2e.py --keep       # just the end-to-end walkthrough; keeps its screenshots
python scripts/gen_openapi.py      # regenerate TypeScript API types after changing the backend
```

The end-to-end walkthrough starts its own API, web app and a scripted stand-in model on free ports with a fresh data folder, then drives a real browser through onboarding, the command palette, an agent whose risky action waits for approval, the demo objective to verification, memory and search, a workflow built in the editor and run twice, audit-log verification, shortcuts, an idea and an overdue to-do on the timeline, and every page at 1440 and 390 pixels wide with basic accessibility checks. It needs a Playwright browser (`pnpm exec playwright install chromium`); without one it reports itself as skipped.

## Security posture in one paragraph

The API listens on loopback only, requires a bearer token on every call (except a minimal liveness ping), rejects foreign `Host` and `Origin` headers, and rate-limits requests. Secrets live in the OS keychain (or a private file, reported as *degraded* in System Health) and are never returned by the API or written to logs. Agents can only *propose* actions; a policy engine that no text can influence decides what runs, and the event log is hash-chained so tampering is detectable. Details and limits: [`docs/SECURITY.md`](docs/SECURITY.md).
