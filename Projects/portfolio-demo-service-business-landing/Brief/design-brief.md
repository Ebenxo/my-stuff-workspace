# Design Brief — Portfolio Demo: Local Service Business Landing Page

Date: 2026-09-17
Requested by: owner (self-initiated, for portfolio/business-pilot purposes — see Business-Ops\00-Business-Plan.md)

## 1. What is this?
A single-page responsive landing page for a fictional local service business, built as a **portfolio/demo piece** — not a real client project. Purpose is to have a concrete, checkable, reusable asset to show prospects and link from proposals (Business-Ops\02-Proposal-Template.md), since there is no real client history yet.

## 2. Purpose / goal
Demonstrate build quality (clean layout, responsive, accessible) and speed. Structure and CSS should be easy to reskin (swap colors/logo/copy) for different verticals — dental, fitness, home services, consulting — so it doubles as the base template for the productized "Small Business Landing Page" service (Business-Ops\04-Service-Catalog.md).

## 3. Audience
End audience (fictional): local customers looking to book/contact a service business. Real audience: prospective freelance clients evaluating whether to hire the owner.

## 4. Must-haves
- [x] Hero section with clear value prop + primary CTA (book/contact)
- [x] Services/offerings section
- [x] Social proof (testimonials)
- [x] About/trust section
- [x] Contact/CTA section with fictional form (no real backend/submission)
- [x] Footer with fictional business info
- [x] Fully responsive (mobile, tablet, desktop) — no horizontal overflow
- [x] CSS variables for colors/fonts so it can be reskinned per future client in minutes

## 5. Must-avoid
- No real business names/logos/testimonials — everything is clearly placeholder/fictional.
- No frameworks/build step (no Node.js in this environment) — plain HTML/CSS/vanilla JS only.
- No stock-photo dependency — use CSS/SVG shapes or clearly-labeled placeholders instead of downloading images, to avoid licensing questions on a demo piece.

## 6. Brand context
New, fictional brand for this demo: "Bright Path Dental" (chosen as a relatable, universally-understood service vertical). Palette/type kept minimal per DESIGN_WORKFLOW.md default style.

## 7. References
None placed yet — using general current landing-page conventions (clear hero, scannable sections, sticky CTA) rather than copying any specific competitor site.

## 8. Format & deliverables
Responsive single-page site: `index.html` + `styles.css` (+ minimal `script.js` for mobile nav toggle only), viewable directly in a browser with no build step.

## 9. Timeline / priority
No external deadline — built proactively to unblock outreach/proposals.

## 10. Open questions
- Which vertical(s) should the reskin variants prioritize first, once real opportunities are sourced? (Pipeline in Business-Ops\01-Opportunity-Pipeline.csv will inform this.)
