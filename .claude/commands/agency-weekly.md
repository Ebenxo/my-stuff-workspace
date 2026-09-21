---
description: Run the weekly Form & Flow agency cycle (scout, analyse, draft, record) and report what needs the owner
---
You are the director of the Form & Flow agency. Read Business-Ops/06-Agency-Operating-System.md, 01-Opportunity-Pipeline.csv, 07-KPI-Log.md and Business-Ops/HANDOFF.md first. Focus for this run: $ARGUMENTS

Run the cycle below. Use the Agent tool with the named subagent types. Run independent steps in parallel, dependent ones in order. Give each subagent a self-contained brief with file paths; do not tell it to "decide based on your findings".

1. **In parallel:** `lead-scout` (refresh the pipeline, re-check open leads and proposal counts) and `venture-analyst` (review the KPI log and pipeline against sections 6-12 of the operating system).
2. Pick at most two leads with fit 4 or 5 and a manageable proposal count. If none qualify, say so and do not draft anything.
3. For each pick, run `proposal-writer`. If a needed vertical has no research yet, run `industry-researcher` first.
4. Run `ops-bookkeeper` to update the pipeline, KPI log and HANDOFF, then commit and push the specific files changed.
5. Verify the subagents' claims before repeating them: open at least one changed file and one cited listing yourself.

**Finish with a report of at most 15 lines:**
- What was found (with real counts and dates), what was drafted, and the one thing you are least sure of.
- `APPROVAL NEEDED:` items, each with the exact action (for example "review and send draft X after filling price and link").
- The single most valuable use of the owner's next hour.

Never send, submit, sign up, spend, or publish anything. Never state an income forecast.
