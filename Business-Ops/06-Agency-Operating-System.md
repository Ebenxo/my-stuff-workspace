# Form & Flow: Agency Operating System

Last updated: 2026-09-21. Owner: ebenezeraaron001@gmail.com

## 1. The honest premise

A team of AI agents can research, draft, build, check and keep records far faster than one person. It cannot create demand, win trust, or take responsibility for a client. Income here depends on one chain: **real conversations, then trust, then paid work, then real proof.** The agents shorten the work between those steps. They do not replace the owner in any step that involves another person or money.

So the design rule is: **agents prepare, the owner decides and sends.**

## 2. The team

The main Claude session acts as **director**: it reads this file, decides the cycle, dispatches the specialists below (parallel where independent, using the `advisor-orchestrator-worker` and `dispatching-parallel-agents` skills), and reports what needs the owner. Specialists live in `.claude/agents/`.

| Agent | Does | Never |
|---|---|---|
| `lead-scout` | Finds and scores open opportunities from public listings; re-checks proposal counts | Contacts anyone; marks a lead as authorised |
| `industry-researcher` | Sourced brief on a trade: prices, objections, regulation, what competitors hide | Uses unsourced claims |
| `proposal-writer` | Drafts proposals and outreach with `[OWNER: ...]` placeholders | Sends; guesses price, timeline or links |
| `site-builder` | Builds Drafts from a research brief using modern-web-guidance, ui-ux-pro-max and the standards | Promotes to Final; self-approves |
| `qa-reviewer` | Independent read-only review: substance, truth, controls, accessibility, mobile | Edits the build |
| `ops-bookkeeper` | Pipeline, tracker, KPI log, HANDOFF, git commit and push | Records estimates as income; stages everything blindly |
| `venture-analyst` | Blunt strategy review: channels, unit economics, risks, kill criteria | Forecasts income; presents guesses as facts |

Cycles are run with `/agency-weekly` and `/agency-vertical <trade>` (see `.claude/commands/`).

## 3. Approval gates: owner only

Agents stop and write `APPROVAL NEEDED:` before any of these. None can be delegated.

- Sending or submitting anything: a bid, a proposal, an email, a message, a form.
- Creating any account, or entering any password, token or payment detail.
- Spending money: hosting, domains, ads, tools, platform fees.
- Publishing anything: a live site, a post, a case study, a testimonial.
- Promoting a build from Drafts to Final.
- Stating a price, a deadline, a guarantee, or any term of a contract.
- Naming a client or quoting one, which needs that client's written permission.
- Any claim about the owner personally (experience, location, credentials).

## 4. Project lifecycle

1. **Lead** logged by lead-scout (pipeline row, fit and effort scores, proposal count).
2. **Qualify**: fit 4-5, real budget, fewer than about 40 proposals or a direct relationship. Otherwise park it.
3. **Research** (if the vertical is new): industry-researcher writes `Business-Ops/research/<vertical>.md`.
4. **Draft the proposal**: proposal-writer, leaving price, timeline and link as `[OWNER: ...]`.
5. **OWNER GATE: review, fill placeholders, send.**
6. Reply, call, and scope agreed in writing (owner).
7. **Build** in Drafts (site-builder), **QA** (qa-reviewer), fix, re-review (at most two loops).
8. **OWNER GATE: approve, promote to Final.**
9. Client review, one revision round, handover, invoice (owner).
10. Ask the client for permission to show the work and for a real testimonial. Only then add it to the portfolio. Never before.
11. ops-bookkeeper logs everything and pushes to GitHub.

## 5. Weekly rhythm

| Day | Cycle | Owner time |
|---|---|---|
| Mon | `/agency-weekly`: scout, analyst, bookkeeper; a short report | 20 min: read, decide |
| Tue-Thu | Research and build one thing at a time; QA every build | Review drafts, send approved messages |
| Fri | KPI row filled from real counts; two-line reflection | 15 min |

The owner has 40+ hours a week available (confirmed 2026-09-21). Use them on conversations and delivery, not on building more samples.

## 6. Where things honestly stand (facts as of 2026-09-21)

- 4 sample builds and a 12-page portfolio exist locally. **None is hosted. No public URL.**
- 7 leads logged; 4 proposals drafted; **0 sent; 0 replies; 0 clients; 0 income.**
- Marketplace competition observed: one lead went from 34 to 197 proposals in two days; another sat at 61. Several bidders have 400+ reviews at 5.0. A zero-review newcomer competes at a disadvantage on price-led marketplaces.
- No Freelancer.com account, no hosting account, no confirmed hours, budget, location or income target.
- Two versions of "Form & Flow" exist: the Codex-built concept site (`FormAndFlow/`, navy and lime) and this portfolio (bone and cobalt). They need one canonical home (see section 13).

## 7. Strategy: hypotheses to test, not forecasts

Each one has a smallest test and a stop condition. None of the numbers below is a prediction.

**H1. Marketplaces are a low-odds channel for a newcomer, worth using selectively.**
Test: bid only where proposals are under about 40 and the brief matches a researched vertical. Track replies. Stop after 10 bids with zero replies.

**H2. Direct outreach to local businesses in researched verticals has the best upside.**
The studio's differentiator (industry-specific, honest sites) is easiest to show to a business whose current site is thin, generic or missing. Each message must contain a specific, true observation about that business's site and one concrete improvement. Test: 20 tailored messages over two weeks, all owner-reviewed and owner-sent, respecting data-protection and anti-spam rules where the owner lives. Stop and rethink after 40 messages with no reply.

**H3. The fastest route to real proof is three discounted first projects in exchange for permission to publish the case study and an honest testimonial.**
It costs margin, not integrity, as long as the discount is disclosed to the client and the testimonial is unedited and real.

**H4. A fixed-scope first offer beats bespoke quoting.**
One scoped starter project (see the FormAndFlow "starter package" wording) makes effort predictable and quotes fast. Price is a hypothesis to test in conversation, not a number to publish until the owner sets it.

**H5. Sourced notes and case studies earn trust with clients who search before they buy.**
Slow, and likely to matter only after the site is hosted and indexed. Do not expect leads from it within weeks.

## 8. Vertical queue (for `/agency-vertical`)

Chosen for repeatable local demand, a clear price or scope objection, and low regulatory risk. Unvalidated: confirm demand with real listings before investing.

1. Plumbing and drain services (quote and callout-fee objections; done for appliance repair, so the pattern transfers).
2. HVAC and heating repair (seasonal urgency; licence rules vary by place, research first).
3. Electricians (licensing is central; claims must be careful).
4. Physiotherapy and similar clinics (health claims need professional review; higher risk).
5. Driving instructors (simple offer; price and area heavy).
6. Mobile pet groomers and dog walkers (area, price, trust in the home).

## 9. Unit economics worksheet (owner fills in)

Effective hourly rate = (price minus platform fee minus tool costs) divided by all hours, including research, revisions and messages that led nowhere.

| Input | Value |
|---|---|
| Intended project price | unknown, owner to set |
| Platform fee (Freelancer.com; verify current rate) | unknown, verify |
| Tool and hosting costs per project | unknown |
| Hours: research, build, QA, revisions, admin | unknown |
| Target hourly rate | unknown, owner to set |

Do not judge any channel until this is filled in with real hours.

## 10. Risks and things only the owner can handle

- **Legal and tax:** business registration or trading status, tax on freelance income, a written contract and invoice template, and data-protection rules for any outreach. Agents are not lawyers or accountants; get proper advice where the stakes justify it.
- **Health, legal and financial claims** in a client's site need review by a qualified professional.
- **AI disclosure:** the About page states that AI assistants are used and results are checked by the owner. Clients may ask; answer honestly. Do not claim work you did not do or credentials you do not have.
- **Reputation:** one fake review or invented statistic would undo the studio's whole positioning.
- **Overreach:** spreading across many verticals before one produces a paying client.

## 11. Owner inputs still missing

1. ~~Hours, country, timezone~~ **Answered 2026-09-21:** based in Lagos, Nigeria (WAT, UTC+1); wants GLOBAL clients, not only local; 40+ hours a week. Still missing: monthly budget ceiling and income target for the first three months. Implications (payment receiving, outreach law by destination, trust for a Nigeria-based newcomer) are being researched in `Business-Ops/research/global-from-lagos.md`.
2. Any real past paid work (even informal), so proposals stay truthful.
3. Hosting and a Freelancer.com account, each created by the owner.
4. Price and timeline for the first offer.
5. Studio name, personal name and photo, and whether to use them.

## 12. Continue, adjust or stop

- **End of week 4:** are 4 proposals or messages actually sent, and is the KPI log honest? If nothing has been sent, the bottleneck is owner time or nerve, not leads. Fix that first.
- **End of week 8:** if 20+ owner-sent contacts produced no replies, change the message or the channel, not the design. If replies exist but no calls, change the offer.
- **First paid project:** run the full lifecycle, then get permission and a real testimonial (H3).
- Stop a tactic when its stop condition is met, and write down why.

## 13. Backlog (first tasks for the agents)

1. **Accessibility fix across all samples and the portfolio:** add skip links and `id`/`tabindex` on `main` (found by the `modern-web-guidance` accessibility guide), then re-review. Owner-visible change; Drafts first.
2. **Host the portfolio** (owner creates account; see `05-Hosting-Setup-Guide.md`).
3. **Canonical site: DECIDED 2026-09-21 by the owner: `FormAndFlow/` (Codex) is the public site.** `Projects/portfolio-studio-site/` becomes source material: the four case studies, the "what I will not ship" standards, the notes and the process page are candidates to port into FormAndFlow, done by Codex or by Claude only with the owner's explicit permission to edit that folder. Until then do not edit `FormAndFlow/` from Claude, and do not publish the portfolio as a second Form & Flow site.
4. **Research the next vertical** (plumbing) and build the next sample only after the owner confirms the direction.
5. **Add real conversion evidence** the moment any exists (calls, replies, wins). Until then the KPI log stays honest and short.
