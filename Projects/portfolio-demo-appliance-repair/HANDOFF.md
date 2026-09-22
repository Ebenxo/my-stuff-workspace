# Handoff — Portfolio Demo: Residential Appliance Repair

This file is the shared memory between Claude Code and Codex (and any human collaborator) for this project. Neither tool sees the other's chat history — **update this before ending a session**, and **read it before starting one**.

## Current status
Done — built, checked, promoted to `Final\`. Fictional business ("Halloway Appliance Repair"), built specifically to demonstrate a genuinely industry-specific, non-generic site per the owner's explicit anti-"AI slop" checklist request (2026-09-19). Fills a real gap: local trades weren't covered by the first three demos.

## Decisions made
| Date | Decision | Reasoning |
|---|---|---|
| 2026-09-19 | Grounded every factual claim in real web research rather than invented numbers | Owner's checklist specifically flags invented stats/vague claims as a generic-AI-site tell; used real diagnostic fee ranges, the real 50% repair-vs-replace rule, real appliance lifespans, and the correct EPA Section 608 certification name. See sources below. |
| 2026-09-19 | Deliberately omitted testimonials, review scores, and "trusted by" logos entirely | Checklist calls fabricated trust signals "serious credibility problems regardless of who built the site" — chose to skip the section rather than fake-but-label it |
| 2026-09-19 | All CTAs are real `tel:`/`sms:` links, no fake contact form | Checklist flags forms that "show success even though nothing was sent" — since there's no backend, a form would have to fake success. `tel:`/`sms:` links are honest and actually functional in a real browser. |
| 2026-09-19 | Chose Barlow Condensed (utility/nameplate feel) over Inter/Space Grotesk | Checklist and the artifact-design guidance both flag Inter/Space Grotesk as the "safe," overused AI-site default; this needed to read as a trade business, not a software startup |
| 2026-09-19 | Explicit exclusions section (small appliances, commercial equipment, HVAC, new gas lines) | Directly answers the checklist's "no explanation of what is excluded" gap |

## Research sources
- [Appliance Repair Diagnostic Fee: What $99 Buys](https://bozmanfix.com/appliance-repair-pricing-transparency/) — diagnostic fee ranges ($60-120), waiver-on-approval norm
- [The Appliance 50% Rule Explained](https://howlongitlasts.com/the-appliance-50-rule-explained/) — repair-vs-replace two-condition rule
- [EPA Section 608 Technician Certification](https://www.epa.gov/section608/section-608-technician-certification) — certification types, Type I for small appliances
- [Appliance Lifespan Guide](https://metroappliancesandmore.com/blog/how-long-do-appliances-last) — lifespan ranges by appliance type

## Changes log
| Date | Tool (Claude Code / Codex) | What changed | Files touched |
|---|---|---|---|
| 2026-09-19 | Claude Code | Built full single-page site (utility bar, hero, appliance grid, brands, process, repair-vs-replace, pricing, exclusions, technician, service area, FAQ, closing, footer) | Drafts\index.html, Drafts\styles.css |
| 2026-09-19 | Claude Code | QA'd in-browser (mobile 375px and a mid-width ~628px both confirmed); found and fixed a real bug — header nav/logo wrapped awkwardly between 620-900px because the stack-to-column breakpoint was too narrow. Fixed by widening that breakpoint to 860px. Promoted to Final. | Drafts\styles.css, Final\* |
| 2026-09-22 | Claude Code | Backported refinements that had been made directly to the public site's copy of this sample without ever reaching this project's own `Final\`: added `design.css` (workshop-inspired refinement pass), an equipment-illustration SVG in the hero panel, revised demo-banner and hero copy, and a "H." initial in the previously-blank technician-photo placeholder. Reconciled from `Projects\portfolio-studio-site\Final\sample\halloway\`, which now matches `FormAndFlow\dist\samples\halloway\` exactly. | Final\index.html, Final\design.css (new) |

## Verification results
| Date | Checked | Result |
|---|---|---|
| 2026-09-19 | Typography | Pass — condensed display face for headings/UI labels, humanist sans for body, consistent scale |
| 2026-09-19 | Spacing | Pass — same 8px-based scale as the other three demos |
| 2026-09-19 | Contrast & accessibility | Pass by inspection — ink-soft on off-white bg is the same contrast family already computed for other demos (~5.9-6.3:1); `focus-visible` outlines present; `<details>/<summary>` used for FAQ (real, functional, keyboard-accessible — not a fake accordion) |
| 2026-09-19 | Mobile layout | Pass — confirmed at 375px and ~628px in-browser; found and fixed a real header-wrapping bug in the 620-900px range (see above) |
| 2026-09-19 | Desktop layout (4-col appliance grid, 2-col hero/pricing) | **Not visually confirmed this session** — same browser-pane desktop-emulation quirk noted in the other demo projects' handoffs. CSS Grid patterns match what's already visually verified elsewhere. Manual check recommended before relying on this for a live proposal. |
| 2026-09-19 | Content specificity (owner's anti-generic checklist) | Self-reviewed against the full checklist the owner provided — no fabricated stats/testimonials, real industry terminology and pricing mechanics, explicit exclusions, named technician with correct real-world credential, functional (not fake) CTAs. Recommend the owner spot-check this against the checklist too, since self-review has blind spots. |

## Open questions / blockers
- Desktop-width visual confirmation still pending (tooling limitation, not a code concern).
- Not yet tied to a specific live pipeline opportunity — this was built to fill a category gap (local trades) rather than chase one specific listing, so it's ready whenever a matching opportunity appears.

## Next steps
1. Manual desktop-width check recommended (same as the other three demos).
2. When a local-trade opportunity (plumber, HVAC, electrician, appliance repair, etc.) appears in the pipeline, this is the demo to reference.
3. If a real bid is placed and won, duplicate this project as the real client's; keep this one as the permanent portfolio reference.
