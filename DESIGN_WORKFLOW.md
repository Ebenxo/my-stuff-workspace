# Design Workflow

This is the shared reference for every design project in this workspace. Both **Claude Code** and **Codex** should read this file before starting work, and should treat it as the source of truth for structure, conventions, and process.

Last updated: 2026-09-17

---

## 1. Preferences (fill in / confirm with owner)

> Confirmed items below; still-open items remain placeholders — update as they're answered.

- **Main design work:** Websites, brand identity, social graphics, and presentations — a mix, all in scope.
- **Visual style default:** Minimal / clean — lots of whitespace, restrained palette, simple type. Use this as the default direction unless a project's brief says otherwise.
- **Primary brand (if any):** _[not yet confirmed — do we have an existing brand to work from, or is each project a fresh brand?]_
- **Preferred fonts:** _[none set — use system/web-safe fonts and Google Fonts by default]_
- **Preferred color approach:** _[none set — default to accessible, WCAG-AA-compliant palettes; lean toward the restrained/minimal palette style given the visual style default above]_

---

## 2. Folder structure

```
D:\my stuff\
├── DESIGN_WORKFLOW.md      ← this file
├── CLAUDE.md                ← points Claude Code here
├── AGENTS.md                 ← points Codex here
├── Projects\                 ← one folder per real project
│   └── <project-name>\
│       ├── Brief\            ← the design brief for this project
│       ├── References\       ← moodboards, competitor examples, inspiration
│       ├── Drafts\           ← work in progress, iterations, exploration
│       ├── Final\             ← approved, finished deliverables only
│       ├── Assets\           ← images/fonts/icons used in this project
│       └── HANDOFF.md        ← shared log: decisions, changes, checks, next steps
├── Brand-Assets\             ← reusable brand assets (logos, colors, fonts) not tied to one project
│   ├── Logos\
│   ├── Colors\
│   ├── Fonts\
│   └── Guidelines\
├── References\               ← general inspiration not tied to a specific project
├── Templates\                ← reusable starting points (see below)
│   └── new-project\          ← copy this folder to start a new project
├── Exports\                  ← optional: copies of finished work staged for sharing/sending out
└── Temp\                     ← scratch space, safe to clear anytime
```

**Rules:**
- New design work stays inside `D:\my stuff` unless explicitly told otherwise.
- **Drafts vs Final is strict**: nothing goes in a project's `Final\` folder until it's been visually checked (see Section 5) and the owner has approved it. `Drafts\` can be messy; `Final\` should always be clean and current.
- `Exports\` is optional — use it only when you need a copy of finished work staged outside the project folder (e.g. to zip and send to a client). The project's own `Final\` folder is always the authoritative copy.
- `Temp\` is disposable. Nothing important should live there long-term.

---

## 3. Project naming

- Project folders: `kebab-case`, descriptive, e.g. `acme-coffee-rebrand`, `q4-launch-landing-page`.
- Files inside a project: prefix with a short version/date tag when iterating, e.g. `homepage-v1.html`, `logo-concept-a.svg`, `2026-09-17-feedback.md`.
- Never overwrite a prior draft in place if it represents a meaningfully different direction — save as a new version instead so history isn't lost.

---

## 4. Standard workflow (per project)

1. **Understand the brief.** Fill out `Templates/design-brief.md` in the project's `Brief\` folder. If the owner hasn't given enough detail, ask specific questions rather than guessing on things that matter (audience, purpose, must-haves).
2. **Inspect references.** Look at anything placed in `References\` (project-level or global `Brand-Assets\`/`References\`). Note what to borrow and what to avoid.
3. **Propose a direction.** Before building extensively, summarize the intended direction (layout, tone, color, type) briefly and check it matches the brief — especially for brand identity or a first homepage layout, where a wrong direction is expensive to unwind.
4. **Build.** Work in `Drafts\`. Keep it editable — plain HTML/CSS, SVG, or other editable source files over flattened images wherever possible.
5. **Check the result visually.** Actually open/render the output (browser for web work, image viewer for graphics) before calling it done. Don't declare success from code/markup alone — see Section 5 for the checklist.
6. **Save final deliverables separately.** Once approved, copy the finished files into `Final\`, and log the outcome in `HANDOFF.md`.

---

## 5. Quality checks before calling something "done"

Run through these before moving work from `Drafts\` to `Final\`:

- **Typography:** consistent font families/weights, a clear type scale (not ad-hoc sizes), readable line length and line height.
- **Spacing:** consistent spacing scale (e.g. 4/8px increments), no cramped or randomly-uneven gaps.
- **Contrast & accessibility:** text meets WCAG AA contrast (4.5:1 normal text, 3:1 large text/UI); don't rely on color alone to convey meaning; images have alt text; interactive elements are keyboard-reachable where relevant.
- **Mobile layout (for web/UI work):** check narrow-width behavior, not just desktop — no horizontal overflow, tap targets big enough, text still readable.
- **Brand consistency:** matches the project's (or global) brand colors, fonts, logo usage rules, and tone — check against `Brand-Assets\Guidelines\` or the project's brand guidelines doc.

Log the result of this check in the project's `HANDOFF.md`, even briefly (what was checked, what passed, what was fixed).

---

## 6. Tools available in this environment

See the "Design tools" note left in `Templates\` and ask before any tool is installed, any account connected, or any file uploaded to a third-party service. Summary as of setup:

- **Canva Desktop** — installed. Good for social graphics, presentation decks, quick templated layouts. Files created there live outside this filesystem's plain-text control (Canva's own format) — export finished work into the project's `Final\` folder as PNG/PDF/etc.
- **Windows Paint / Photos** — installed (built-in). Basic raster viewing/light editing only.
- **No Node.js, git, ImageMagick, Inkscape, GIMP, or Adobe apps detected.** Web design work in this workspace defaults to plain HTML/CSS/SVG opened directly in a browser — no build step required. If a project needs image conversion, SVG optimization, or batch processing, that requires installing a tool — ask first.
- **No design-tool accounts (Figma, Adobe, Canva API, etc.) are connected.** Nothing gets uploaded to any of these without asking first, project by project.

---

## 7. Claude Code ↔ Codex collaboration

Claude Code and Codex do **not** share chat history or memory. The only shared context is what's written to disk. So:

- Every project has a `HANDOFF.md` (from `Templates/project-handoff.md`). Whichever tool works on a project **must** update it before finishing a session:
  - What was decided and why
  - What changed (files touched)
  - What was verified (the Section 5 checklist) and the result
  - What's next / open questions
- Don't assume the other tool remembers anything not written down. If a decision was made in conversation but not logged, it effectively didn't happen for the other tool.
- Read the project's `HANDOFF.md` at the start of any session before making changes.

---

## 8. Starting a new project

1. Copy `Templates\new-project\` into `Projects\<project-name>\`.
2. Fill in `Brief\design-brief.md`.
3. Drop any reference material into `References\`.
4. Follow the workflow in Section 4.
