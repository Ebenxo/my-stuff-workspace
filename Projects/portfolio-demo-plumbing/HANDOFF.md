# Handoff — Kestrel Bend Plumbing (fictional residential plumbing sample, Texas)

Shared memory between Claude Code and Codex. Read before starting; update before ending.

## Current status
Draft v1 built in Drafts\ (index.html + styles.css) by the site-builder agent on 2026-09-21. NOT reviewed. Awaiting independent qa-reviewer, then owner. Nothing in Final\.

## Decisions made
| Date | Decision | Reasoning |
|---|---|---|
| 2026-09-21 | Name "Kestrel Bend Plumbing", sample area Round Rock, Pflugerville, Georgetown, Cedar Park; phone (512) 555-0147 | One Bing search found no plumbing company by that name (results were irrelevant, so weak evidence; DuckDuckGo blocked by CAPTCHA). Number is in the reserved fictional 555-01xx block. |
| 2026-09-21 | Palette: ink #1c2624, page #f5f6f3, verdigris tint #e4ece9, verdigris #0b5d57, copper #9a4419, copper tint #f4e1d3. Type: Zilla Slab (headings) + IBM Plex Sans (body) | Distinct from charcoal/amber/Barlow, pine/paper/Newsreader, bone/cobalt/Bricolage, paper-navy/Source Serif, navy/lime/Arial. No blue drop or wrench. |
| 2026-09-21 | Layout: page reads like paperwork (glance sheet, sample written quote, dashed leaders); left rail + body columns; tables for prices, after-hours, water heater, licence | Answers the quote/fee questions rather than decorating them. |
| 2026-09-21 | Sample policy: $95 fee (band $75-150), credited in full on same-visit approval or return within 14 days; after-hours $150 fee (band $150-250); multipliers 1.5x / 2x / 2.5x labour (band 1.5-3x); labour $110/h (band $80-130); no calls answered 10pm-7am | All inside sourced bands and labelled sample on the page. |
| 2026-09-21 | Sample job prices: drain $185, toilet repair $165, faucet repair $155, disposal repair $185, minor leak $240, WH repair $325, WH replace tank $1,750 | Each inside the research bands (see research section 2). Toilet/faucet replacement, tankless and sewer camera deliberately unpriced. |

## Changes log
| Date | Tool | What changed | Files touched |
|---|---|---|---|
| 2026-09-21 | Claude Code (site-builder) | Built Draft v1 | Drafts\index.html, Drafts\styles.css, HANDOFF.md |

## Verification results (builder self-checks, NOT approval)
| Date | Checked | Result |
|---|---|---|
| 2026-09-21 | Horizontal overflow, headless Chrome, iframe widths 320/375/414/768/1100/1440 | scrollWidth == viewport at all widths after fix. First run overflowed 20px at 320 (grid min-content, then the quote table); fixed with minmax(0,1fr) and tighter padding under 30rem. Iframe viewport is width minus 15px scrollbar (360 at "375"). |
| 2026-09-21 | Contrast, computed WCAG ratios | ink/page 14.3, muted/page 7.3, muted/tint 6.6, verdigris/page 7.1, verdigris/tint 6.4, white/copper 6.5, copper/page 6.0, copper/tint 5.4, ink/copper-tint 12.3, white/ink 15.5, copper-tint/ink 12.3. All pass AA. Table header white on #0b5d57 is above 7. |
| 2026-09-21 | Links over http (python http.server 127.0.0.1:8767, stopped after) | All 9 in-page anchors resolve, no duplicate ids, styles.css 200. tsbpe.texas.gov 200, regionalh2o.org 200, psc.wi.gov 200 (HEAD timed out once, curl GET 200). tel:/sms: only, no forms. |
| 2026-09-21 | Structure | Skip link, header/nav/main(id=content, tabindex=-1)/footer, headings h1 then h2/h3 with no skips, no headings inside summary, captions and th scope on all 5 tables, :focus-visible outline 3px copper, prefers-reduced-motion honoured (smooth scroll and transitions). |
| 2026-09-21 | Visual | Screenshots at 375 and 1280 read for the first screen only. Lower sections were measured, not viewed. |

## Not verified / for qa-reviewer
- Only the top of the page was visually inspected; tables at 320-375 need eyeballing.
- No screen reader or keyboard walk-through run. No physical device.
- Google Fonts load from the network; fallback stack (Rockwell/Georgia, Segoe UI) not visually checked.
- Name check is weak (see decisions).
- Scope/refer-out list (research section 7) is entirely SEARCH-ONLY, so it is written as the sample firm's policy and labelled so on the page.
- Tank-leak-means-replace line is not stated by any source; labelled on the page as the sample firm's position.
- Regional Water Providers Consortium page is Portland-area; the page says so and does not claim it applies to Texas.

## Research claims not used
- Frozen-pipe steps (SEARCH-ONLY, and the brief excludes them).
- DOE/Energy.gov lifespan figures (unopened); only Fuse Service READ ranges used.
- Angi figures (SEARCH-ONLY) except the $995 camera average, mentioned only to explain why camera work is not priced.
- Parts-markup 200-400% and "30% higher satisfaction" (unnamed sources), deposit-cap claim, Roto-Rooter "no hidden charges".
- "Open windows" advice on gas; electrical-caution line; Florida and California licence rules; "about 45 states" count; membership plans.
- Toilet/faucet replacement prices and any single camera price (research says not to publish without an owner-set price).

## Open questions / blockers
- Owner: approve the fictional name and the sample service area (real Texas towns named as sample).

## Next steps
1. qa-reviewer independent review of Drafts\ (accessibility, mobile tables, claim check against research).
2. Fix findings, then owner review. Only then copy to Final\.
