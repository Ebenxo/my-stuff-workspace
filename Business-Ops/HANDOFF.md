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
