# Owner checklist: everything only you can do

Updated 2026-09-21. Order matters. Time estimates are guesses. Costs come from the $70 budget; prices marked "unverified" must be checked at checkout. Claude and the agents never do these steps for you: they involve accounts, money, or your name.

## Do you need to worry about a back end? No.
The Form & Flow site is plain static files: HTML, CSS and a little JavaScript for the demo. There is no server, database or code to maintain, and nothing to secure or keep running. Netlify (or any static host) just serves the files.
- The enquiry "demo" on the homepage runs only in the visitor's browser and sends nothing anywhere. That is by design and is labelled.
- Real contact is a plain email link. Nothing can break or leak.
- You would only need a back end if you later sell a real working enquiry form (Tier 2). Then you would use a form service that emails you, not build one.

## Does it push to GitHub? Yes, now including the public site.
- Everything in `D:\my stuff` (plans, samples, case-study source, agents, docs) is committed and pushed to your private repo `Ebenxo/my-stuff-workspace`.
- **Gap found and fixed today:** the public site folder `FormAndFlow\dist` has its own separate git repo (Codex's), which the main repo ignores, so it was NOT being pushed. It is now mirrored into `Exports\formandflow-site` by `scripts\sync-formandflow-site.py`, and the bookkeeper agent runs that before each commit.
- Netlify Drop (below) deploys a folder you drag in. It does not read GitHub, so after any site change you drag the updated `FormAndFlow\dist` folder in again (about 1 minute). Optional later upgrade: a separate GitHub repo for the site connected to Netlify so pushes deploy automatically. Ask me when you want it.

---

## A. This week: get the site online and start conversations

### 1. Send the first 5 warm-network messages by **2026-09-24** (about 1-2 hours) [free]
Needs no site and no accounts. List up to 25 people who run a small business or know someone who does. Tell me 5 names and what each person does, and I draft short personal messages. You edit and send them yourself. Log each one (sent date, reply) so I can update the KPI log.

### 2. Make three decisions so I can finish the site (30 minutes) [free]
1. About block: your name, whether to say you are in Lagos, and the AI wording. Draft is in `10-Offer-and-Site-Fixes-Draft.md`.
2. Hero line naming who the studio is for (draft in the same file).
3. The first-project offer: confirm the $200 "one page" scope, and whether to publish any price yet.

### 3. Put the site online with Netlify Drop (15-30 minutes) [free]
1. Go to app.netlify.com/drop and create a free account (your own email).
2. In File Explorer open `D:\my stuff\FormAndFlow` and drag the whole **`dist`** folder onto the drop area.
3. Netlify gives you an address ending in `.netlify.app`. Open it on your phone and click through the Work pages, a sample and the Notes.
4. Optional: Site configuration, then Change site name, to something clean.
5. Send me the address. I will update the notes and drafts with it.
Deploy the folder called `dist` itself, not `FormAndFlow` and not `Exports`.

### 4. Ask your bank three questions (about 1 hour) [free]
1. What is the fee for receiving an incoming USD wire?
2. Can the account receive from Payoneer, and are there restrictions?
3. Do foreign credits arrive as naira or dollars, and does the bank need a registered business name to open a dollar account?
Write the answers down. Payment planning depends on them.

### 5. Buy the domain (30 minutes) [budget cap $25 first year]
- Target: **formandflow.co**. It was unregistered when checked on 2026-09-21 (registry lookup); `formandflow.com` is already registered by someone else.
- Compare the total at checkout at one or two registrars. A promotional first-year price of about $15.76 with a renewal of about $31.20 was seen at one registrar on 2026-09-21 (unverified how long the promotion runs). Renewal prices are usually higher than year one: note it.
- Turn on domain privacy if it is free. Decline extras (hosting, email, site builders, SSL add-ons). You do not need them.
- Check your card works for international online payments before you start. Ask your bank if unsure (unverified: a USD virtual card is a common way).
- Connect it to Netlify: Domain management, Add a domain, then follow Netlify's instructions to point the domain at it (either change the nameservers to Netlify's or add the records it shows). The HTTPS certificate is issued automatically by Netlify. DNS can take from minutes to a few hours.
- Keep using your Gmail address for now. Add a domain email later.
Do this after the site is online, and do not let it delay sending messages.

### 6. Set up how you get paid (1-2 hours) [free to open, fees when used]
- Create a Payoneer account (your legal name must match your ID and bank account name; a government ID is required). Opening is free. Check the real withdrawal fee to a Nigerian bank inside the dashboard before you quote a price: reported minimums up to $20 would be 10% of a $200 payout.
- Only create a Freelancer.com account if you decide to place a marketplace bid. Marketplaces are a low-odds channel right now.
- Never send passwords or ID to me or to any agent.

### 7. Check the name (1-2 hours) [free searches; fees only if you register]
- CAC name availability search in Nigeria for "Form & Flow".
- Trademark searches for "Form & Flow" in web design and software: Nigeria, US (USPTO), UK (IPO).
- Check social handles and marketplace profile names.
- Registration (CAC business name) is reported at about NGN 10,000-25,000 (unverified). Only pay if the bank or Payoneer requires it, or you are ready.

## B. Weeks 2-4

### 8. Get an accountant answer (when income is near) [cost unknown]
Use the 12 questions in `research/global-from-lagos.md` section 6: trading form, tax registration, foreign income, VAT on exports, deductions, records. Book it before the first payment arrives if you can afford it, or right after.

### 9. Write plain terms for clients (1-2 hours, I can draft) [free]
A one-page agreement: scope, one revision, price, deposit or milestone, client supplies content, client owns domain and hosting, how you get paid, what happens if they stop replying. I can draft it for you to edit. For real use, have a lawyer read it.

### 10. If you do US cold email: get a postal address first [cost unknown]
Every US commercial email needs a valid postal address in it (FTC CAN-SPAM guide: a street address, a USPS-registered P.O. box or a registered private mailbox). Decide which. Not needed for personal warm-network messages. Do not email UK sole traders (need consent). Avoid cold email to Canada and Germany.

### 11. Send the 20-message US outreach test (about 10-12 hours) [free]
Only after the site is online. I prepare the research and drafts. You review, edit and send each one. Log minutes and replies.

### 12. Run the weekly rhythm (about 35 minutes a week)
- Monday: read the weekly report (`/agency-weekly` in a session), decide, send approved messages.
- Friday: fill the real numbers into the KPI log (sent, replies, calls, wins, cash, hours).

## C. Budget map ($70)
| Item | Cap |
|---|---|
| Domain (year one) | $25 |
| Reserve, keep unspent | $10 |
| Everything else in sections A and B | $0 planned (accountant, CAC and postal address costs are unknown; they may not fit in $70; tell me if you want to prioritise) |

## D. Checkpoints
- **2026-09-24:** 5 warm messages sent, and Netlify account created. If not, fix time or nerve first.
- **2026-09-28:** site online, bank answers in hand, payment route chosen.
- **2026-10-05:** 20 messages or pitches sent and logged.
- **2026-10-21:** 40+ sent across at least 3 channels; a first price quoted to a real person.

## E. What I do so you can focus on this
Draft messages and proposals, refresh leads weekly, research the next trade, build and QA samples, keep the KPI log and plan current, apply your site decisions, mirror the site into GitHub and push. I never send, sign up, spend, publish a claim about you, or state a price on your behalf.
