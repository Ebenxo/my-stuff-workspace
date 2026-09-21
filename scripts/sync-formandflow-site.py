r"""Mirror the public Form & Flow site into this repo so it is backed up to GitHub.

Why: D:\my stuff\FormAndFlow\ has its own git repo (Codex's), which this repo ignores, so a normal push here would
not include the public site. This copies FormAndFlow\dist (the deployable folder) into Exports\formandflow-site,
which IS tracked. It never touches FormAndFlow\ itself and never copies anything except dist.

Run:  python scripts/sync-formandflow-site.py
Then commit Exports/formandflow-site with the rest of the work (the ops-bookkeeper agent does this).
"""
import os, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "FormAndFlow", "dist")
DST = os.path.join(ROOT, "Exports", "formandflow-site")

if not os.path.isfile(os.path.join(SRC, "index.html")):
    sys.exit("No index.html in " + SRC + ": refusing to sync.")

if os.path.isdir(DST):
    shutil.rmtree(DST)
shutil.copytree(SRC, DST)
count = sum(len(f) for _, _, f in os.walk(DST))
size = sum(os.path.getsize(os.path.join(d, x)) for d, _, f in os.walk(DST) for x in f)
print(f"mirrored {count} files ({size/1024:.0f} KB) to {DST}")
