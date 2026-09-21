# Handoff - Studio Portfolio Site

## Status
Expanded 2026-09-21 and promoted to Final: 12 pages + 4 live sample copies. Not yet hosted; no public URL.

## Structure
- Home (hero, work index, notes, standards, contact), Work, Process, About, Notes (index + 3 articles), 4 case studies.
- Each case study has a live window (iframe onto `sample/<slug>/`, resizable on desktop) plus brief, research with sources, decisions, what was left out, what would be measured, and what went wrong or is unfinished.
- Projects: Halloway Appliance Repair, Marlow Street Dental (rebuilt; replaces the earlier Bright Path Dental sample), Studio Noir, Eleanor Voss. `Final/sample/*` are copies of each sample project's Final folder. Re-copy if a sample changes.
- Generator: `build.py` (Python) writes all pages into Drafts. Edit content there, run it, then copy Drafts to Final. Python is at `C:/Users/HP/AppData/Local/Programs/Python/Python312/python.exe`.

## Decisions
- Honest framing everywhere: all projects are labelled samples for fictional businesses; no client work, reviews, awards or stats are claimed.
- Palette: bone grey #ebebe7, ink #121212, cobalt #1f3bd1 (single accent). Type: Bricolage Grotesque / Instrument Sans / IBM Plex Mono.
- Contact is a mailto link only, matching the address already published on FormAndFlow. No personal name or photo yet (owner has not supplied one).
- No JavaScript on the portfolio itself.
- Notes cite sources where they make factual claims. The "emergency room for trouble swallowing or breathing" advice is flagged as ordinary safety practice, not sourced to the ADA.

## Owner must confirm or edit before publishing
1. About page says: "I use AI coding assistants for research and drafting, and I check the results myself." True to the workflow used here, but it is a public claim about the owner. Confirm or reword.
2. Studio name "form & flow", the email address, and the line "Open to first client projects".
3. Process page says "Your domain and hosting stay in your name" and "one round of changes". These are business terms; confirm they match what the owner will offer, and keep them consistent with FormAndFlow's package wording.
4. Health content on the dental sample is fictional. A real dental client needs clinician and legal review.

## Verification (2026-09-21)
- All 12 pages: no horizontal overflow at 375px (measured through a 375px frame). Internal link and asset check: 0 broken.
- Live window verified loading the real sample when the folder is served over http (title, H1 and background read from inside the frame). It does not load from file:// in this sandbox; on any real host it works.
- Case page, work page and dental sample screenshot-checked at phone width. Desktop width not visually confirmed (browser-pane limitation).
- Not done: contrast tool check (ink on bone is high contrast by inspection; ink-2 #4a4a46 on #ebebe7 estimated about 6.6:1), keyboard walkthrough beyond presence of focus styles, Lighthouse or other performance measurement.

## Next
- Host it (Netlify Drop guide in Business-Ops). Deploy the whole Final folder.
- Replace samples with real client work as it exists; add a personal name or photo if wanted.
