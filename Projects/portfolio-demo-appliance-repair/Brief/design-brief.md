# Design Brief — Portfolio Demo: Residential Appliance Repair

Date: 2026-09-19
Requested by: owner — explicit request to build a well-researched, industry-specific site and deliberately avoid generic "AI website" patterns (owner supplied a detailed anti-generic checklist, largely matching Nielsen Norman Group's findings on generic AI-prototype appearance).

## 1. What is this?
A fourth portfolio/demo piece: a single-page website for a fictional small, owner-operated residential appliance repair business ("Halloway Appliance Repair"). Not a real client.

## 2. Purpose / goal
Demonstrate a genuinely industry-specific build — one a plumber or software company could *not* just reskin — by grounding every section in real appliance-repair-industry facts (researched via web search, sources below) rather than generic marketing copy. Also fills a real gap in the demo library: local trades (appliance/HVAC/plumbing-style) are a very common real client type for this freelance business, and none of the first three demos (dental clinic, creative portfolio, personal bio) cover that category.

## 3. Audience
End audience (fictional): homeowners with a broken appliance, deciding whether to call this business. Real audience: prospects evaluating this as a portfolio sample.

## 4. Research grounding (so content is real-industry-accurate, not invented)
- Diagnostic fees industry-wide run $60-120, commonly credited toward the repair if the customer approves the work same visit. Used **$79, credited if approved**.
- The "50% rule" for repair-vs-replace: replace if the repair cost exceeds 50% of a comparable new unit's price *and* the appliance has already passed 50% of its expected lifespan — both conditions, not just cost alone.
- Average appliance lifespans: refrigerators ~10-15 yrs, washers ~10-14 yrs, dryers ~10-13 yrs, dishwashers ~9-12 yrs.
- EPA Section 608 (Clean Air Act) certification is legally required for anyone servicing equipment that could release refrigerant — Type I covers small appliances (residential refrigerators/freezers). Used as the technician's real, correctly-named credential.
- Sources: [Appliance Repair Diagnostic Fee: What $99 Buys](https://bozmanfix.com/appliance-repair-pricing-transparency/), [The Appliance 50% Rule Explained](https://howlongitlasts.com/the-appliance-50-rule-explained/), [EPA Section 608 Technician Certification](https://www.epa.gov/section608/section-608-technician-certification), [Appliance Lifespan Guide](https://metroappliancesandmore.com/blog/how-long-do-appliances-last).

## 5. Must-haves (directly answering the owner's anti-generic checklist)
- [x] State what's actually sold, to whom, and where (specific appliance types, specific fictional service-area towns, explicit exclusions)
- [x] Real pricing/process mechanics: diagnostic fee amount and exactly when it's waived, warranty length, what happens if a part must be ordered
- [x] A genuinely useful "repair vs. replace" explainer using the real 50% rule, not vague reassurance
- [x] Named technician with a real, correctly-named certification (EPA 608 Type I) and a specific tenure, not "our team of experts"
- [x] Explicit list of what this business does **not** do (small countertop appliances, commercial equipment, HVAC/central air, new gas line runs)
- [x] Every button that appears clickable actually works: `tel:` and `sms:` links only (no fake contact-form "message sent" behavior, since there's no backend to actually send anything)
- [x] No fabricated trust signals: no testimonials, no fake review scores, no "trusted by" logos, no invented stats

## 6. Must-avoid (per the owner's checklist, non-exhaustive highlights)
- No purple-blue gradient / glassmorphism / neon-on-navy "startup" aesthetic — this is a blue-collar trade business, not software.
- No pill-shaped announcement bar, no floating dashboard screenshot, no bento grid, no 3-tier "Most Popular" pricing (pricing here isn't tiered — it's a flat, transparent diagnostic-fee model).
- No numbered 3-step oversimplification of the repair process — describe the real sequence (call/text → scheduled arrival window → diagnosis + upfront quote → same-visit repair or part order → warranty) with real specificity.
- No testimonial carousel or fabricated review scores — skip trust-signal sections entirely rather than fake them.
- No generic AI-safe fonts (Inter/Space Grotesk) — chose a condensed, utilitarian sans (nameplate/equipment-label feel) instead.
- No stock photos of smiling technicians/handshakes — CSS-only graphic treatment, consistent with the other three demos.

## 7. Brand context
New fictional persona/business, distinct from the other three demos: warm parts-catalog off-white + charcoal ink + burnt-amber accent, condensed utilitarian typography — reads as "hardware/trade," not "software startup."

## 8. Format & deliverables
1 static HTML page + stylesheet: `index.html`, `styles.css`.

## 9. Timeline / priority
Built proactively per owner's explicit request this session.

## 10. Open questions
None blocking. This is a demo/portfolio piece, not tied to a specific live pipeline opportunity yet — but local-trade sites are a common enough real client type that this should help win one when it appears.
