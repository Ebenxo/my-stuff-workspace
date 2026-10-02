#!/usr/bin/env python3
"""Build the browser preview: the real web app as one self-contained page, with no API behind it.

    python scripts/build_preview.py      # writes apps/web/dist-preview/nexus-os-preview.html

The preview answers the API inside the page (`apps/web/src/preview/`): ideas, notes and to-dos, the
timeline, projects and settings work and are saved; agents, models, tools and workflows say they need
NEXUS on the person's computer. The output is page content for a host that supplies the document
skeleton (claude.ai Artifacts); every script, style, font and image is inlined into it.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"
DIST = WEB / "dist-preview"
OUT = DIST / "nexus-os-preview.html"
MAX_BYTES = 15 * 1024 * 1024  # artifact pages may be up to 16 MB

# The host's skeleton resets body styles outside any cascade layer, which beats the app's
# `@layer base`; restate the app's own base so it looks the same as when it runs locally.
BASE = """
html, body, #root { height: 100%; }
body { margin: 0; background: var(--nx-canvas); color: var(--nx-fg); font-family: var(--font-sans);
  font-size: 14px; line-height: 1.5; font-feature-settings: "cv11", "ss01"; -webkit-font-smoothing: antialiased; }
:root { color-scheme: dark; }
:root[data-theme="light"] { color-scheme: light; }
"""


def main() -> int:
    pnpm = shutil.which("pnpm")
    if not pnpm:
        print("Need `pnpm` on PATH.", file=sys.stderr)
        return 1
    built = subprocess.run(  # noqa: S603
        [pnpm, "--filter", "@nexus/web", "exec", "vite", "build", "--mode", "browser-preview"], cwd=ROOT, check=False
    )
    if built.returncode != 0:
        return built.returncode

    index = (DIST / "index.html").read_text(encoding="utf-8")
    scripts = re.findall(r'<script type="module"[^>]*src="\./([^"]+)"[^>]*></script>', index)
    styles = re.findall(r'<link rel="stylesheet"[^>]*href="\./([^"]+)"[^>]*>', index)
    if len(scripts) != 1:
        print(f"Expected one script in the build, found {scripts}", file=sys.stderr)
        return 1
    leftovers = [p.name for p in (DIST / "assets").iterdir() if p.suffix not in {".js", ".css"}]
    if leftovers:
        print(f"Assets were not inlined: {leftovers}", file=sys.stderr)
        return 1

    css = "\n".join((DIST / s).read_text(encoding="utf-8") for s in styles)
    js = (DIST / scripts[0]).read_text(encoding="utf-8").replace("</script", "<\\/script")
    page = (
        "<title>NEXUS OS</title>\n"
        f"<style>{css}\n{BASE}</style>\n"
        '<div id="root"></div>\n'
        f'<script type="module">{js}</script>\n'
    )
    OUT.write_text(page, encoding="utf-8")
    size = OUT.stat().st_size
    print(f"\n  wrote {OUT.relative_to(ROOT)} ({size / 1024 / 1024:.1f} MB)")
    if size > MAX_BYTES:
        print("  too large for a hosted page", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
