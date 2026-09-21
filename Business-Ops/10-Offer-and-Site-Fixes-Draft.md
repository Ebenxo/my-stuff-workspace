# Offer tiers and site fixes: DRAFT for owner approval

From the strategy review of 2026-09-21. Nothing here is on the public site yet. Every item marked APPROVAL NEEDED is your call. Claude may edit `FormAndFlow/dist` (you said so) but will not publish a price, a personal claim or a payment term without your yes.

## 1. Why the homepage package does not match the $200 plan
The homepage `#package` lists four items: a landing page, a form with one destination, a follow-up status with a reply template, and one revision with handover. The 90-day plan's $200 scope is narrower (one page, client supplies content). A buyer who reads the homepage would expect all four for $200, which cannot be done in about 5 hours. Also, the follow-up system is a browser-memory demo, not something a client can actually run yet.

## 2. Proposed tiers (hypotheses to test; prices other than $200 are placeholders)
| Tier | Contents | Price | Test |
|---|---|---|---|
| 1. One page | One mobile page, tel/sms/mailto links, client supplies text and photos, one revision, handover | **$200** (your test price) | First 3 buyers finish within 5 hours with hours logged. If 2 of 3 overrun, cut scope or raise price before selling more. |
| 2. Page plus enquiry form | Tier 1 plus a form that emails one address, a reply template as a document, two revisions | [OWNER: set a price; the plan used $400-500 only to illustrate] | Quote it as an alternative to every tier-1 enquiry. Signal: at least 1 of the first 5 quotes chooses it. Stop: 0 of 8 choose it, revisit price or contents. |
| 3. Follow-up system or monthly care | Not offered yet | n/a | Offer only when there is a working, testable deliverable. Until then, sell a scoped quote after a paid audit. |

Log the usual unpaid hours on every job (discovery call, content chasing, domain and hosting set-up) so the real hourly rate is known.
APPROVAL NEEDED: the tier-2 price, and whether to publish any price at all yet.

## 3. Site fixes
**Done by Claude (2026-09-21, in `build.py`, regenerated into `dist`):**
- "Hand-written HTML and CSS" changed to "Plain HTML and CSS" (the pages come from generators and AI-assisted builds, so "hand-written" was not accurate).
- Removed or softened claims I had not verified: "competitors tend to bury" the fee, "most practices give a range or nothing", and "nationally" or "commonly" price ranges (now "in the sources I read").
- Added to the Work page: "Made with AI assistance, stated openly."

**Needs your decision:**
1. **Say who you are.** The site says "I" but shows no name, place or photo, and the footer says "Working studio name". Suggested block (edit freely, then tell me to add it):
   > **About.** Form & Flow is [YOUR NAME], working from Lagos, Nigeria, with clients on UK and US hours. I build small service-business websites. The research, drafting and checks are done with AI assistants, and every sourced claim on this site links to its source. There is no client work yet; the projects here are samples for fictional businesses.
   APPROVAL NEEDED: your name, whether to state Lagos, and the AI wording.
2. **Say who it is for in the hero.** The headline names no buyer. Suggested line under "Good form. Better flow.": "Websites for repair, trade and clinic businesses that say what you charge, what you do and what you do not." Add a link to one live sample above the fold. APPROVAL NEEDED: wording.
3. **Rewrite `#package` to match Tier 1** (and mention Tier 2 as "with an enquiry form"). This is Codex's copy; you have said I may edit. APPROVAL NEEDED: price wording, or leave "price follows scoping" until you have tested $200 in conversations.
4. **UK buyers have no UK sample.** Do not pitch UK buyers with the US samples until one exists.
5. **Contact.** A Gmail address is fine to start. For US cold email every message needs a valid postal address (FTC CAN-SPAM guide, read 2026-09-21: a street address, a USPS-registered P.O. box or a registered private mailbox). Decide which you will use before any cold email; warm-network messages do not need it.
