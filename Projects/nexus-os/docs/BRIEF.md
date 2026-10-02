# NEXUS OS — improved brief

The owner's original prompt (60+ sections) was rewritten into this brief before any code was written. The original intent is unchanged. This brief adds what the original left open: priorities, resolved contradictions, environment limits, and testable acceptance criteria. Where this brief and the original prompt differ, this brief records the decision and the reason.

## 1. One-paragraph product

NEXUS OS is a local-first agentic operating system. A user gives a high-level objective; a Planner turns it into a dependency graph of tasks; an Orchestrator delegates each task to a specialist agent; agents act only through a mediated Tool Registry → Policy Engine → Sandbox → Event Log pipeline; sensitive actions pause for human approval; a Critic and Verifier check the work; results are saved as versioned artifacts and (with visibility) memory. The user watches all of it live.

## 2. Priorities

| Tier | Meaning | Contents |
|---|---|---|
| **P0** | The MVP fails without it | Backend runtime (providers, agent loop, tools, permissions, approvals, sandbox, planner, orchestrator, critic/verifier, artifacts, events, memory), SQLite + migrations, local API with auth, UI for: command center, project workspace (chat, execution graph, files, artifacts, memory, activity), approvals, agents, provider settings, health |
| **P1** | Required by the MVP definition of done | Workflows (visual editor + engine + re-run), scheduler, MCP client, usage dashboard + budgets, command palette, onboarding, demo project |
| **P2** | Designed for, not built | Skills packages, swarm strategies beyond Single/Pipeline/Parallel/Reviewer, computer-use agent, browser agent, voice, mobile, cloud sync, multi-user, marketplaces |

P2 items get typed extension points (interfaces, registries, docs) so they can be added without rewrites. They do not get placeholder code.

## 3. Contradictions and gaps found in the original prompt, and decisions

1. **`packages/agents|tools|memory|workflows|providers|permissions|observability` vs a Python backend.** These are backend concepts and the prompt puts the orchestration layer in Python. Decision: they live as modules in `services/api/app/`. `packages/` holds only TypeScript packages that exist: `ui`, `shared`, `schemas`.
2. **`services/api` vs `services/orchestrator`.** Two processes would add IPC for no MVP benefit. Decision: one Python service; `app/orchestration` is a strict module boundary (it depends on interfaces, never on FastAPI), so it can be split into its own worker process later.
3. **`apps/web` and `apps/desktop`.** Decision: the React UI lives in `apps/web`. `apps/desktop` is the Tauri shell that wraps the built web app and supervises the Python sidecar. One UI codebase, two hosts.
4. **"Terminal" panel vs "never give agents unrestricted machine access".** A raw PTY would bypass the permission layer. Decision: the bottom "Agent Terminal" is a live stream of tool output, logs, events and errors plus a NEXUS command line (`/plan`, `/run`, …). It is not a shell. A user-driven shell, clearly separate from agents, is a later option.
5. **"Approve For Session" vs "VERY_HIGH must always require approval".** Decision: VERY_HIGH is never session-grantable. HIGH session grants are scoped to the tool within the project and expire when the backend restarts or the user revokes them.
6. **Scheduled workflows vs "never act dangerously in silence".** Decision: unattended runs never auto-approve MODERATE-or-above actions beyond the project's explicit policy. If no human is present the run parks in `NEEDS_APPROVAL` and raises a notification.
7. **`reasoningMode` field vs "never expose hidden reasoning".** Decision: `reasoningMode` only controls provider-side thinking budgets. Thinking output is discarded and never stored or shown. Agents emit a one-sentence action summary per step; that is the only rationale the system keeps.
8. **Model prices.** Prices change and cannot be verified from this environment. Decision: the model catalog ships capability and context data only where reliable; prices are user-editable and `null` means "unknown" (shown as such, never guessed). Budgets enforce on tokens always and on USD only where a price is known.
9. **Providers.** Gemini, OpenAI-compatible, LM Studio and custom endpoints were listed for later phases. LM Studio and custom endpoints are OpenAI-compatible and Gemini is a small REST adapter, so all are built in Phase 2 with Anthropic, OpenAI and Ollama.
10. **No live API keys, no GUI, no webkit in the build environment.** Decisions: (a) all adapters are verified against mock HTTP servers, and this is stated wherever it applies; (b) a clearly labelled scripted **Demo provider** drives the demo project and the E2E test; (c) the Tauri shell is scaffolded but cannot be compiled here, so it is documented as unverified.
11. **Windows.** The owner's workspace is on Windows (`D:\my stuff`). The backend must not depend on POSIX-only features. Resource limits (`resource.setrlimit`) are applied where available and the sandbox reports which limits are actually enforced on the current OS.
12. **Repo placement.** Workspace rules keep new work under `Projects/<kebab-name>/`. NEXUS OS lives at `Projects/nexus-os/`. The design-project `Drafts/Final` split does not apply to a code project; `HANDOFF.md` and `docs/BUILD_STATE.md` carry state.

## 4. Non-negotiable engineering rules (from the original, kept verbatim in spirit)

Typed contracts everywhere · migrations only · every important action emits an event · every dangerous action passes the policy engine · no hidden reasoning stored or shown · no secrets in source or logs · external content is untrusted data · every async UI operation has loading, success and error states · every agent run is recoverable · finish a phase (lint, typecheck, tests, build, run) before starting the next.

## 5. Acceptance criteria (mapped to the 20-point MVP definition)

Each item is checked by an automated test unless noted. The E2E test drives the real UI against the real backend with the scripted Demo provider.

| # | MVP item | Verified by |
|---|---|---|
| 1 | Launch locally | `scripts/dev` boots API + web; health API test; E2E |
| 2 | Connect a provider | provider CRUD + test-connection API tests (mock upstream); onboarding E2E |
| 3 | Create a project | API test; E2E |
| 4 | Give an objective | API test; E2E |
| 5 | Planner creates tasks | orchestration test with scripted provider; E2E |
| 6 | See a task graph | React Flow component test; E2E screenshot |
| 7 | Orchestrator delegates | orchestration test (assignments recorded) |
| 8 | Multiple agents work | orchestration test (≥3 distinct agents in one objective) |
| 9 | Agents use tools | agent-loop test; ToolCall rows |
| 10 | Review tool activity | Activity/Tool Calls panel E2E |
| 11 | Approve restricted actions | approval flow tests (once / session / deny / edit); E2E |
| 12 | Read/write project files | filesystem tool tests incl. traversal and symlink escapes |
| 13 | Receive artifacts | artifact versioning tests; E2E |
| 14 | Critic reviews | orchestration test (review→revise loop) |
| 15 | Verifier checks | orchestration test (PASS / PARTIAL / FAIL paths) |
| 16 | Store project memory | memory service tests incl. sensitive-data refusal |
| 17 | Search memory | semantic + keyword retrieval tests |
| 18 | Create a reusable workflow | workflow API + editor test |
| 19 | Re-run a workflow | workflow engine test; run history |
| 20 | Inspect full activity log | event log API + hash-chain verification test |

## 6. Scope honesty for this build session

Built and verified here: backend runtime, API, web UI, tests, E2E with the Demo provider. Not verifiable here and documented as such: live calls to Anthropic/OpenAI/Gemini/Ollama, Tauri compilation and OS keychain integration on Windows/macOS, Docker sandbox mode.
