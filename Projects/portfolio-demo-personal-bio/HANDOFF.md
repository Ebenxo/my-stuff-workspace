# Handoff — Portfolio Demo: Classic Personal Bio Page

This file is the shared memory between Claude Code and Codex (and any human collaborator) for this project. Neither tool sees the other's chat history — **update this before ending a session**, and **read it before starting one**.

## Current status
Done — built, checked, promoted to `Final\`. Fictional persona ("Eleanor Voss"), built to match a real, live Freelancer.com opportunity ("Classic Personal Bio Website", £250-750 GBP, logged in `Business-Ops\01-Opportunity-Pipeline.csv`).

## Decisions made
| Date | Decision | Reasoning |
|---|---|---|
| 2026-09-19 | Built as a single static page (no multi-page structure) | Matches the source brief exactly — a one-page bio, explicitly structured so sections can be appended later without a rebuild |
| 2026-09-19 | Kept all copy in English, did not attempt Chinese text | The real brief asks for the client's own bio in Chinese (个人简介) — that's the client's content to supply, not something to fabricate for a demo. The demo shows the layout/typography treatment only. |
| 2026-09-19 | Distinct third palette (muted paper/ink/navy, serif type) | Other two demos use warm cream/green and off-white/terracotta — this one needed its own identity so all three don't read as reskins of one template |

## Changes log
| Date | Tool (Claude Code / Codex) | What changed | Files touched |
|---|---|---|---|
| 2026-09-19 | Claude Code | Built single-page site + stylesheet | Drafts\index.html, Drafts\styles.css |
| 2026-09-19 | Claude Code | Verified in browser (mobile 375px confirmed clean, no overflow; contrast checked by calculation, ~5.9:1 for body text, passes AA), promoted to Final\ | Final\index.html, Final\styles.css |
| 2026-09-22 | Claude Code | Backported refinements that had been made directly to the public site's copy without ever reaching this project's own `Final\`: added `design.css`, a masthead line and a refined portrait monogram ("e." / "WORDS & RECORDS"), replaced the placeholder "This page is intentionally quiet..." copy and the "What's next" stub with real "Areas of focus" content, and pointed the contact section at the actual case-study page instead of a bare "#" link. Reconciled from `Projects\portfolio-studio-site\Final\sample\eleanor-voss\`, which now matches `FormAndFlow\dist\samples\eleanor-voss\` exactly. | Final\index.html, Final\design.css (new) |

## Verification results
| Date | Checked | Result |
|---|---|---|
| 2026-09-19 | Typography | Pass — single serif family (Source Serif 4) for display/body, sans-serif utility labels for eyebrow/nav-style text, consistent scale |
| 2026-09-19 | Spacing | Pass — same 8px-based spacing scale as the other two demos |
| 2026-09-19 | Contrast & accessibility | Pass — ink-soft (#5c5a52) on paper (#f4f2ec) computes to ~5.9:1, exceeds 4.5:1 AA; focus-visible outline present |
| 2026-09-19 | Mobile layout | Pass — confirmed at 375px in-browser: portrait/title stack vertically, no horizontal overflow |
| 2026-09-19 | Brand consistency | N/A — new standalone demo brand |

## Open questions / blockers
- None blocking. Depends on owner's decision to pursue the matching pipeline opportunity.

## Next steps
1. Reference this piece from a tailored (unsent, owner-review) proposal in `Business-Ops\Proposals-Drafts\` for the matching opportunity.
2. If a real bid is placed and won, duplicate this project as the real client's; keep this one as the permanent portfolio reference.
