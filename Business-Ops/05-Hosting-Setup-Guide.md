# Hosting Setup Guide — Get the Two Demo Sites Live

Decision made 2026-09-17: use free static hosting (Netlify) instead of a Claude-hosted link or file attachments, so proposal links look like a normal portfolio/project link. This is a one-time, ~10 minute task — **only you can do the account-creation step**, per this workflow's own guardrails.

## Why Netlify Drop
No git, no command line, no build step needed — literally drag a folder onto a page and it's live. Both demo sites are plain HTML/CSS/JS with no server-side code, so this works as-is.

## Steps (repeat once per demo site)

1. Go to **https://app.netlify.com/drop** in your browser.
2. If prompted, sign up for a free account (email, GitHub, or Google login all work) — this is the one step that has to be you.
3. Once logged in, drag the entire **`Final`** folder (not the parent project folder — just `Final`) onto the drop zone:
   - First site: `D:\my stuff\Projects\portfolio-demo-service-business-landing\Final`
   - Second site: `D:\my stuff\Projects\portfolio-demo-creative-grid\Final`
4. Netlify deploys instantly and gives you a live URL like `random-name-123.netlify.app`.
5. Optional but recommended: click **Site settings → Change site name** to something cleaner, e.g. `bright-path-dental-demo.netlify.app` and `studio-noir-demo.netlify.app`.
6. Repeat for the second folder — each becomes its own separate Netlify site with its own URL.

## After you have both URLs
Paste them here and I'll drop them into the matching proposal drafts:

- `portfolio-demo-service-business-landing` live URL: _______________
- `portfolio-demo-creative-grid` live URL: _______________

Then I'll update:
- `Proposals-Drafts\2026-09-17_clean-portfolio-site-design.md`
- `Proposals-Drafts\2026-09-17_3-page-portfolio-html-build.md`
- `01-Opportunity-Pipeline.csv` (clear the "no public link" blocker note)

## Alternative (if you'd rather use GitHub Pages instead)
Also free, also no command line needed:
1. Create a GitHub account at github.com if you don't have one.
2. Create a new repository, e.g. `portfolio-demo-dental`.
3. On the repo page, use **Add file → Upload files**, drag in everything from the project's `Final\` folder, commit.
4. Go to **Settings → Pages**, set source to the `main` branch / root, save.
5. GitHub gives you a URL like `yourusername.github.io/portfolio-demo-dental` within a minute or two.
6. Repeat for the second site as a second repository.

Netlify Drop is faster for this use case (no repo setup); GitHub Pages is worth it if you'd rather have the source code visibly hosted on GitHub too (some clients like seeing that).
