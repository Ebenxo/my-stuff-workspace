# Handoff — Portfolio Demo: Local Service Business Landing Page

This file is the shared memory between Claude Code and Codex (and any human collaborator) for this project. Neither tool sees the other's chat history — **update this before ending a session**, and **read it before starting one**.

## Current status
Done — built, checked, and promoted to `Final\`. This is a fictional portfolio/demo piece (not a real client site), created to support the freelance business pilot tracked in `Business-Ops\` at the workspace root. Ready to link from real proposals.

## Decisions made
| Date | Decision | Reasoning |
|---|---|---|
| 2026-09-17 | Built a fictional local-service-business (dental clinic) landing page rather than a real client project | No real client yet; needed a concrete, checkable asset to point proposals at (see Business-Ops\02-Proposal-Template.md) |
| 2026-09-17 | Structured CSS with variables (`:root` tokens for color/font/spacing) instead of hard-coded values | Makes this reusable as the base template for the "Small Business Landing Page" productized service — reskin per vertical/client by editing tokens, not rewriting layout |
| 2026-09-17 | No stock photos; used CSS shapes/gradients for visual interest instead | Avoids image licensing questions on a demo piece and keeps the file dependency-free |

## Changes log
| Date | Tool (Claude Code / Codex) | What changed | Files touched |
|---|---|---|---|
| 2026-09-17 | Claude Code | Built full single-page responsive site (hero, services, about, testimonials, CTA band, contact form, footer) | Drafts\index.html, Drafts\styles.css, Drafts\script.js |
| 2026-09-17 | Claude Code | Verified in browser at desktop (1440px) and mobile (375px) widths, checked accessibility contrast math, promoted to Final\ | Final\index.html, Final\styles.css, Final\script.js |

## Verification results
| Date | Checked | Result |
|---|---|---|
| 2026-09-17 | Typography | Pass — 2 font families (display serif for headings, sans for body), consistent `clamp()`-based type scale, no ad-hoc sizes |
| 2026-09-17 | Spacing | Pass — single 8px-based spacing scale (`--space-1` through `--space-7`, 8/16/24/32/48/64/96px) used throughout |
| 2026-09-17 | Contrast & accessibility | Pass — computed WCAG contrast ratios: body text ~6.3:1, button text ~6.0:1, eyebrow labels ~5.9:1 (all exceed 4.5:1 AA for normal text); focus-visible outlines present on all interactive elements; decorative visuals marked `aria-hidden` |
| 2026-09-17 | Mobile layout | Pass — verified at 375px and 1440px in-browser: nav collapses to hamburger below 720px, card grids reflow from 4→2→1 columns, no horizontal overflow, contact form stacks single-column |
| 2026-09-17 | Brand consistency | N/A — new standalone demo brand, no existing guidelines to check against |

**Note:** the built-in browser tool used for QA sandboxes local files (blocks external stylesheets/scripts, allows only inline CSS), so verification was done against a temporary inlined-CSS copy of the same styles — the shipped multi-file version (external `styles.css`/`script.js`) should render identically in a normal browser but hasn't been re-screenshotted in that exact form. Worth a quick manual open-in-Chrome/Edge spot check before showing to a real prospect.

## Open questions / blockers
- Which vertical(s) to reskin next depends on real opportunities sourced into `Business-Ops\01-Opportunity-Pipeline.csv` — none sourced yet.
- Mobile nav-toggle JS (`script.js`) works by DOM inspection/logic review but couldn't be interactively clicked-tested in the sandboxed preview (script execution blocked there) — worth a manual click check in a real browser.

## Next steps
1. Manually open `Final\index.html` in a real desktop browser (double-click it) to confirm external CSS/fonts/JS load and the mobile nav hamburger actually toggles.
2. Once real opportunities exist, duplicate this project as a new one per client/vertical and reskin via the CSS `:root` tokens rather than rebuilding from scratch.
3. Add this as the first entry in `Business-Ops\04-Service-Catalog.md` once a real sale validates pricing/timing.
