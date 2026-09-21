# HANDOFF — Business-Ops

## 2026-09-17 — Claude Code
**Decided:** Adopted Model A (productized freelance web design/landing pages via Upwork/Fiverr + direct outreach, built fast with Claude Code) as the starting income model, based on a 3-model comparison (time to first payment, cost, difficulty, acquisition, repeatability). Model B (AI automation retainers) planned as phase-2 upsell once case studies exist.

**Changed:** Created `Business-Ops/` folder with:
- `00-Business-Plan.md` — assumptions, model comparison, guardrails, decision log, open questions
- `01-Opportunity-Pipeline.csv` — tracker for finding/verifying/ranking opportunities
- `02-Proposal-Template.md` — truthful proposal drafting template
- `03-Financial-Tracker.csv` — income/cost/time tracker
- `04-Service-Catalog.md` — empty until first pilot validates a repeatable package

**Verified:** N/A yet — no client work has started.

**Blockers / open questions:**
- Owner's real weekly hours, budget ceiling, location/timezone, and any real past paid work are still unconfirmed (see open questions in 00-Business-Plan.md).
- No opportunities have been sourced, verified, or contacted yet — pipeline CSV is empty.
- Waiting on owner authorization before any outreach, platform application, or spend.

**Next steps:**
1. Confirm assumptions with owner.
2. ~~Source 5-10 real opportunities into the pipeline CSV.~~ Done for this pass (see below) — refresh regularly, listings expire in ~6 days.
3. ~~Score and rank them.~~ Done for this pass.
4. Draft (not send) 2-3 tailored proposals for owner review, once owner picks which opportunities to pursue.
5. Get explicit go-ahead before any contact or bid submission.

---

## 2026-09-17 (same session, part 2) — Claude Code
**Decided:** Built a portfolio/demo piece since there was no case study to point proposals at yet.

**Changed:**
- Created `Projects\portfolio-demo-service-business-landing\` — a fictional local-service-business (dental clinic) landing page, built and quality-checked per `DESIGN_WORKFLOW.md` Section 5, promoted to that project's `Final\`. Reusable as the base template for the "Small Business Landing Page" service (CSS variables make it easy to reskin per vertical). See that project's own `HANDOFF.md` for full details.
- Sourced 5 real, currently-live opportunities from Freelancer.com's public job listings into `01-Opportunity-Pipeline.csv`, scored by fit/effort. Top two ("Clean Portfolio Site Design", "3-Page Portfolio HTML Build") are strong fits — vanilla HTML/CSS, no backend, budgets $120-130.
- Note: Upwork blocked automated browsing (Cloudflare bot check) and Reddit is blocked by this session's browsing safety restrictions, so Freelancer.com was the only source reached this pass. Fiverr doesn't expose public buyer requests without an account. Widening sourcing later may need the owner to browse Upwork/Fiverr directly and share postings, or a login-based approach.

**Verified:** Portfolio piece checked in-browser at desktop (1440px) and mobile (375px) — see project HANDOFF for full results (typography, spacing, contrast math, mobile, all pass).

**Blockers:**
- Still waiting on owner's real hours/budget/location/income-target/past-experience answers.
- No bids/applications submitted — owner authorization required before contacting or bidding on any of the 5 logged opportunities. Note these are live listings with "6 days left" as of 2026-09-17 — they will expire around 2026-09-23 if not acted on.
- Found: the machine's C: drive is completely full (0 GB free) — unrelated to this project but flagged to owner, may cause broader issues.

**Next steps:**
1. Owner reviews the 5 opportunities in `01-Opportunity-Pipeline.csv` and says which (if any) to pursue.
2. ~~On approval, draft a tailored proposal per `02-Proposal-Template.md`~~ — done proactively for the 2 strongest-fit opportunities, see below.
3. Get explicit go-ahead before submitting any bid.

---

## 2026-09-17 (same session, part 3) — Claude Code
**Decided:** The two best-fit live opportunities ("Clean Portfolio Site Design", "3-Page Portfolio HTML Build") are both personal/creative portfolio-grid sites, which the first demo (a dental/local-business site) didn't match well. Built a second, matching demo instead of forcing the wrong reference into a proposal.

**Changed:**
- Created `Projects\portfolio-demo-creative-grid\` — a fictional creative-portfolio site ("Studio Noir": landing intro, grid gallery, reusable project-detail template), plain HTML/CSS, no frameworks, built and checked per `DESIGN_WORKFLOW.md`, promoted to Final. See that project's `HANDOFF.md` — note desktop-width visual confirmation hit a browser-tool quirk this session and is flagged as a quick manual check still worth doing (mobile width was fully confirmed).
- Drafted two tailored, unsent proposals in `Proposals-Drafts\` (`2026-09-17_clean-portfolio-site-design.md`, `2026-09-17_3-page-portfolio-html-build.md`), each referencing the new demo.
- Updated `01-Opportunity-Pipeline.csv` status for both rows to "Proposal drafted - awaiting owner review/authorization to submit."

**Blockers surfaced by drafting these:**
- **No public link exists for either demo** — they're local files only. To actually send a proposal, the owner needs to either host them somewhere (e.g. GitHub Pages/Netlify — free, but creating an account is the owner's call) or plan to attach files directly through Freelancer.com's bid flow instead of a link.
- Both draft proposals still need a real bid amount and turnaround estimate — left as placeholders for the owner to fill in, since only the owner can commit to a timeline/price.
- Submitting requires a Freelancer.com account, which doesn't exist yet — owner's action/approval needed.
- Both listings show "6 days left" as of 2026-09-17 (~expires 2026-09-23) — there's a real clock on these two.

**Next steps:**
1. Owner reviews both draft proposals and decides: pursue, skip, or edit.
2. ~~Owner decides on hosting approach~~ — decided: free static hosting (Netlify Drop preferred, GitHub Pages as alternative). See below.
3. Nothing gets submitted without the owner's explicit go-ahead.

---

## 2026-09-17 (same session, part 4) — Claude Code
**Decided (by owner, via explicit choice):** Host the two demo sites on free static hosting (Netlify or GitHub Pages) rather than a Claude Artifact link or file-attachment-only bids — a normal-looking portfolio link matters more here than saving the ~10 minutes of setup.

**Changed:** Created `Business-Ops\05-Hosting-Setup-Guide.md` — exact copy-paste steps for Netlify Drop (primary) and GitHub Pages (alternative). No account was created by Claude Code (account creation is explicitly the owner's own action per this workflow's guardrails).

**Blocker:** Waiting on the owner to actually create the account and drag the two `Final\` folders in, then share back the two resulting live URLs.

**Next steps:**
1. Owner follows `05-Hosting-Setup-Guide.md`, gets two live URLs.
2. Once shared, update both proposal drafts and the pipeline CSV with the real links (removes the last blocker on those two drafts besides bid amount/timeline, which only the owner can set).
3. Owner then decides whether to actually submit either bid — still nothing sent without explicit go-ahead.

---

## 2026-09-17 (same session, part 5) — Claude Code
**Decided:** Owner asked to always push this workspace's work to GitHub going forward (standing instruction, saved to Claude's memory as `feedback_git_workflow`).

**Changed:**
- Installed Git for Windows via winget (owner approved).
- Initialized a git repo at `D:\my stuff` root, added a `.gitignore` (excludes `Temp\` and `FormAndFlow\` — see important finding below), made the first commit (47 files, hash `8a78d69`).
- Git identity was already configured on this machine (`user.name = ebenxo`, matching owner's known email) — used as-is for the commit.

**Important finding — read this before touching anything at the workspace root:**
`D:\my stuff\FormAndFlow\` is **not** an empty/leftover folder — it is a separate, actively in-progress project with its own git repository and a configured remote (`origin`), being built live during this very session (files timestamped minutes apart, commits as recent as the session's current time). Almost certainly Codex working concurrently in this shared workspace, per this workspace's own dual-tool design. It contains a `dist/` build (index.html/style.css/app.js), a `qa/` folder with Node `.cjs` scripts, an `.openai/hosting.json`, and its own git history — a real, unrelated project, not something to fold into this repo. It has been explicitly excluded via `.gitignore` (`FormAndFlow/`) so it's never accidentally absorbed as a broken embedded-repo reference again (git initially warned about exactly this on the first `git add -A`). **Do not modify, commit into, or delete anything under `FormAndFlow\`** — it belongs to whatever other session is building it.

**Blocker:** Pushing to GitHub still needs, from the owner:
1. Confirm/provide the exact GitHub username or org to push under (found a plausible hint: local git config has `user.name = ebenxo`, which may or may not match the actual GitHub login — needs owner confirmation, not assumed).
2. Private vs. public repo preference (recommended: private, since `Business-Ops\` will hold real client/financial data over time).
3. Owner creates the actual empty repo on GitHub (Claude Code cannot create it — requires the owner's GitHub login). Suggested: create it empty, no README/license/.gitignore from GitHub's side, so it doesn't conflict with the existing local history.
4. Once the remote exists, Claude Code will run `git remote add origin <url>` and `git push -u origin master` — this should trigger Git Credential Manager's browser-based login for the owner to authenticate directly with GitHub (Claude Code will not see or handle any password/token).

**Next steps:**
1. ~~Owner answers the 3 items above.~~ Done — username `ebenxo`, private repo `my-stuff-workspace` created.
2. ~~Claude Code adds the remote and pushes.~~ Done, with a caveat: the sandboxed shell used by Claude Code cannot complete Git Credential Manager's interactive browser login (`git push` fails instantly with "terminal prompts disabled"). The owner ran the first `git push` from their own terminal instead, which cached the credential in Windows Credential Manager — Claude Code can push normally from here on.
3. Going forward: commit + push after meaningful units of work (a project reaching `Final\`, a Business-Ops update), not after every micro-edit.

**Resolved 2026-09-19:** Repo live at https://github.com/ebenxo/my-stuff-workspace (private). Local `master` in sync with `origin/master` (commits `8a78d69`, `764483a`). `FormAndFlow\` remains excluded via `.gitignore` — still someone else's (likely Codex's) separate in-progress project, do not touch it.

---

## 2026-09-19 (part 2) — Claude Code
**Decided:** Refreshed the opportunity pipeline while waiting on owner inputs elsewhere (Netlify URLs, bid amounts, account creation) — nothing to push forward there, so kept the pipeline itself moving.

**Changed:**
- Re-checked both proposal-drafted opportunities: still **Open** as of today. Important new data point on "Clean Portfolio Site Design" — **61 competing proposals already in**, several bidders with 400+ reviews at 5.0 rating. Worth the owner weighing realistic win odds against a newcomer profile with zero platform history before committing time to that one specifically; "3-Page Portfolio HTML Build" didn't show a visible proposal count on the same pass.
- Added 2 new strong-fit leads to `01-Opportunity-Pipeline.csv`: "Portfolio Site UI/UX & Build" (client explicitly accepts plain HTML/CSS/JS) and "Classic Personal Bio Website" (single page, lowest-effort item in the whole pipeline — client wants Chinese-language content but supplies the text themselves, no translation needed from us).
- Minor data-quality note: one listing's page showed "Posted 1 minute ago" on a revisit two days after first found — likely a Freelancer.com activity-timestamp quirk rather than fake data (bidder usernames/ratings/client history all check out as real), but exact "days left" countdowns shouldn't be treated as precise. Removed the specific "expires ~Sept 23" claim from the pipeline for the two older rows since it can't be confirmed reliably.

**Next steps:**
1. ~~Owner reviews the 2 new leads and decides whether to pursue~~ — proceeded proactively, see below.
2. Still waiting on: Netlify URLs, real bid amounts/timelines for all 4 drafts now, Freelancer.com account creation, and the original 5 business-plan assumptions.
3. Nothing bid or sent — still just pipeline maintenance.

---

## 2026-09-19 (part 3) — Claude Code
**Decided:** Applied the same proven playbook (matching demo + draft proposal) to the 2 new leads found earlier this session, since nothing else was unblocked to work on.

**Changed:**
- Built a third demo project, `Projects\portfolio-demo-personal-bio\` ("Eleanor Voss" — single-page classic/serif personal bio site), to match the "Classic Personal Bio Website" opportunity. Checked at mobile width, contrast computed ~5.9:1 (passes AA), promoted to Final. See that project's own HANDOFF.md.
- Correction while researching this one: the real budget is **£250-750 GBP** (not the $30-250 USD I'd guessed when first logging it) — 34 competing proposals averaging £346. Fixed in the pipeline CSV.
- Drafted 2 more tailored, unsent proposals: `2026-09-19_classic-personal-bio-website.md` and `2026-09-19_portfolio-site-ui-ux-build.md` (the latter reuses the existing `portfolio-demo-creative-grid` demo — no new build needed for that one).
- Updated pipeline CSV: both new rows now "Proposal drafted."

**Note on the bio-page proposal specifically:** the client wants their bio written in Chinese (个人简介). The draft proposal explicitly asks the client to supply that text rather than assuming we'd write/translate it — don't let this slide into an implied translation service without the owner deciding that's actually something to offer.

**Running total: 4 drafted, unsent proposals now waiting on the owner** (2 from 2026-09-17, 2 from today). All have the same 3 blockers: hosting link, real bid amount/timeline, and a Freelancer.com account.

**Next steps:**
1. Owner reviews all 4 draft proposals in `Proposals-Drafts\` and decides which (if any) to actually pursue — with 4 now queued, worth prioritizing rather than trying to bid on all of them.
2. Still waiting on: Netlify URLs, bid amounts/timelines, Freelancer.com account, and the original 5 business-plan assumptions.
3. Nothing bid or sent.

---

## 2026-09-19 (part 4) — Claude Code
**Decided:** Owner asked for a new, well-researched, deliberately non-generic industry site, and provided a detailed checklist of "AI slop" tells to avoid (matching Nielsen Norman Group's published findings on generic AI-prototype appearance). Treated this as a real design brief, not a quick add.

**Changed:**
- Researched the residential appliance-repair industry via web search before writing any copy: real diagnostic fee norms ($60-120, credited if approved), the actual "50% rule" for repair-vs-replace decisions, real appliance lifespans, and the correct EPA Section 608 (Type I) certification name for refrigerant-handling technicians. Sources logged in the project's own HANDOFF.md.
- Built a fourth demo project, `Projects\portfolio-demo-appliance-repair\` ("Halloway Appliance Repair") — fills a real gap, since local trades (plumbing/HVAC/appliance-style businesses) are a common real client type for this freelance business and none of the first three demos covered that category.
- Deliberately built against the owner's checklist: no fabricated testimonials/trust badges, no generic Inter/Space Grotesk font choice, real `tel:`/`sms:` links instead of fake contact-form success states, explicit list of what the business doesn't service, named technician with a real correctly-named credential.
- Found and fixed a real responsive bug during QA: the header nav/logo wrapped awkwardly between ~620-900px width because the stack-to-column breakpoint was too narrow. Widened it to 860px.
- This demo isn't tied to a specific pipeline opportunity yet — it was built to fill the local-trades category gap, ready for whenever a matching lead appears.

**Next steps:**
1. Owner spot-checks this new demo against their own checklist (self-review has blind spots).
2. Manual desktop-width visual check recommended (same known tooling limitation as the other three demos).
3. Still waiting on everything listed above from prior entries — nothing bid or sent.


---

## 2026-09-21 (part 5): Agency operating system - Claude Code
**Decided:** Owner asked for "a full automation agency working together to scale Form & Flow" and help making it a real venture. Built it as a human-gated multi-agent system, not autonomous income: agents prepare, the owner decides and sends. Honest premise recorded in `06-Agency-Operating-System.md`.

**Added:**
- `.claude/agents/`: lead-scout, industry-researcher, proposal-writer, site-builder, qa-reviewer, ops-bookkeeper, venture-analyst. Each has a narrow tool list and the same hard rules (never send, submit, sign up, spend, publish; never invent claims; never touch FormAndFlow/).
- `.claude/commands/`: `/agency-weekly` and `/agency-vertical <trade>` run the cycles (the second stops before Final).
- `Business-Ops/06-Agency-Operating-System.md`: roles, approval gates, project lifecycle, weekly rhythm, facts as of today, five hypotheses (H1-H5) with tests and stop conditions, vertical queue, unit-economics worksheet, risks, missing owner inputs, continue/stop criteria, backlog.
- `Business-Ops/07-KPI-Log.md`: baseline row. Sent 0, replies 0, won 0, cash 0.
- CLAUDE.md and AGENTS.md now point both Claude and Codex at the operating system and state who owns which project.
- Tested that `modern-web-guidance` `search` and `retrieve` work. Its accessibility guide showed the samples and portfolio lack skip links; queued as backlog item 1.

**Not verified:** the agents and commands have not been run. Subagent types load at session start, so they should appear after a fresh session or reload. First real test: `/agency-weekly`. Frontmatter checked structurally only.

**Blockers (owner):** hosting and Freelancer account; hours/budget/location/income target; price and timeline for the first offer; decision on which "Form & Flow" site is canonical (FormAndFlow/ concept site by Codex vs the portfolio); confirm the AI-assistant line on the About page.

**Next:** owner reads section 6-12 of the operating system and answers section 11. Then run `/agency-weekly` in a fresh session.
