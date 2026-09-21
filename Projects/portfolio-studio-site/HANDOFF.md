# Handoff - Studio Portfolio Site

## Status
Built and promoted to Final (2026-09-21). Not yet hosted; no public URL.

## Decisions
- 3 projects, not 4: dental demo excluded (fabricated stats, emoji icons; see brief). Recommend rebuilding it to the Halloway standard.
- Palette: bone grey #ebebe7, ink #121212, cobalt #1f3bd1 (single accent). Type: Bricolage Grotesque (display), Instrument Sans (body), IBM Plex Mono (labels).
- Page structure: label gutter + content rows (spec-sheet layout); work index as large type rows, not a card grid.
- Contact is a mailto link only; the address matches the one already published on FormAndFlow.
- Personal name is not used anywhere (owner has not supplied one); only the working studio name.

## Files
Final/index.html, Final/case/{halloway,studio-noir,eleanor-voss}.html, Final/styles.css, Final/sample/<slug>/ (copies of each demo's Final). build.py regenerates HTML: edit content there, rerun, recopy Drafts to Final.

## Verification
Mobile (~391px) checked for home hero, work list and a case page: no overflow, reads cleanly. Desktop-width not visually confirmed (same browser-pane limitation as other projects). Contrast: ink on bg is high; ink-2 #4a4a46 on #ebebe7 is roughly 6.6:1 (calculated by estimate, not tool-verified). Keyboard focus outlines present; reduced-motion respected; no JavaScript.

## Open
- Owner should confirm the working studio name "form & flow" and the contact email are what they want on this site.
- Owner name/photo/about text if they want a personal element.
- Hosting (Netlify guide in Business-Ops). Sample links use relative paths so they work once the whole Final folder is deployed together.
- Real client work replaces the samples as it exists.
