# Handoff — Portfolio Demo: Creative Portfolio Grid Site

This file is the shared memory between Claude Code and Codex (and any human collaborator) for this project. Neither tool sees the other's chat history — **update this before ending a session**, and **read it before starting one**.

## Current status
Done — built, checked, and promoted to `Final\`. Fictional persona ("Studio Noir"), built specifically to match two real, currently-live Freelancer.com opportunities logged in `Business-Ops\01-Opportunity-Pipeline.csv` ("Clean Portfolio Site Design" and "3-Page Portfolio HTML Build").

## Decisions made
| Date | Decision | Reasoning |
|---|---|---|
| 2026-09-17 | Built as a 3-page site (landing intro, grid gallery, reusable project-detail template) in plain HTML/CSS, no JS framework, no sliders/masonry | Mirrors exactly what both source briefs asked for, so a proposal can honestly point at a build in the same style |
| 2026-09-17 | Used CSS gradient blocks instead of stock/placeholder photos for all "project images" | Avoids image licensing questions on a demo piece (same rule as the dental demo project) |
| 2026-09-17 | Distinct palette/typography from the other demo (`portfolio-demo-service-business-landing`) — warm neutral + terracotta accent vs. that project's green/cream | So the two demo pieces don't look like the same template reskinned when shown together |

## Changes log
| Date | Tool (Claude Code / Codex) | What changed | Files touched |
|---|---|---|---|
| 2026-09-17 | Claude Code | Built 3-page site + shared stylesheet | Drafts\index.html, Drafts\work.html, Drafts\project.html, Drafts\styles.css |
| 2026-09-17 | Claude Code | Verified in browser (mobile width 375px fully confirmed; desktop-width screenshot was inconclusive due to a browser-pane tooling quirk this session, not a suspected CSS issue — see note below), promoted to Final\ | Final\*.html, Final\styles.css |
| 2026-09-22 | Claude Code | Backported a large set of refinements that had been made directly to the public site's copy without ever reaching this project's own `Final\`: added `design.css`, an `art\` folder of 6 original SVG studies, and 5 new individual study pages (`amble.html`, `fieldnote.html`, `marlowe.html`, `northline.html`, `verdant.html`) replacing the old arrangement where all six grid items linked to one shared `project.html` template. Copy also switched from implying real client history ("Brand Identity", years) to honest "self-initiated study" labelling. While reconciling, found and fixed two real bugs that had crept into the live copy: a duplicated "Heron & Co." feature block on `index.html`, and a missing `</footer>` with unclosed `<main>`/`<div>` tags on `work.html`. Reconciled from `Projects\portfolio-studio-site\Final\sample\studio-noir\`, which now matches `FormAndFlow\dist\samples\studio-noir\` exactly (bugs fixed there first, then synced back). | Final\* (all HTML), Final\design.css (new), Final\art\ (new), Final\amble.html, Final\fieldnote.html, Final\marlowe.html, Final\northline.html, Final\verdant.html (new) |

## Verification results
| Date | Checked | Result |
|---|---|---|
| 2026-09-17 | Typography | Pass — single sans-serif family, clamp()-based type scale, consistent hierarchy |
| 2026-09-17 | Spacing | Pass — same 8px-based spacing scale approach as the other demo project |
| 2026-09-17 | Contrast & accessibility | Pass by inspection — ink-soft body text (#6b6f76) on off-white bg (#faf9f6) is structurally the same contrast pattern already computed and confirmed >4.5:1 AA for the other demo; focus-visible outlines present |
| 2026-09-17 | Mobile layout | Pass — confirmed at 375px in-browser: nav/hero/grid (1-column)/project-detail all render cleanly, no horizontal overflow |
| 2026-09-17 | Desktop layout (900px+ grid: 3-col, 640-900px: 2-col) | **Not visually confirmed this session** — the browser pane's desktop-width emulation rendered inconsistently (environment/tooling issue, reproduced across multiple attempts), not something in the page code. The grid CSS uses the identical `display:grid; grid-template-columns: repeat(3,1fr)` + media-query pattern already visually verified working in `portfolio-demo-service-business-landing`, so risk is low, but a manual open-in-real-browser check at desktop width is recommended before relying on this for a live proposal. |
| 2026-09-17 | Brand consistency | N/A — new standalone demo brand |

## Open questions / blockers
- Desktop-width visual confirmation still pending (see above) — quick manual check recommended.
- Depends on `Business-Ops\01-Opportunity-Pipeline.csv` for which real opportunities this supports; those two listings show "6 days left" as of 2026-09-17.

## Next steps
1. Manually open `Final\index.html` in a real desktop browser at full width to confirm the 3-column grid and project two-image layout render as intended (quick pass/fail check, layout is simple).
2. Reference this piece from the tailored (unsent, owner-review) proposals in `Business-Ops\` for the two matching Freelancer.com opportunities.
3. If a real bid is placed and won, duplicate this project as the real client's, keep this one as the permanent portfolio reference.
