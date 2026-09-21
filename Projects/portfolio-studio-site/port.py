"""Port the portfolio's case studies and notes into the Form & Flow site (Codex's dist/) using its design system.
Source of truth for content: build.py in this folder. Writes only NEW files under dist/ plus two idempotent insertions in dist/index.html.
Run:  python port.py [path-to-FormAndFlow-dist]
"""
import os, sys, shutil, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = sys.argv[1] if len(sys.argv) > 1 else r"D:\my stuff\FormAndFlow\dist"
EMAIL = build.EMAIL
MARKET = {"halloway": "United States (fees in USD)", "marlow-street": "United States (fees in USD)",
          "kestrel-bend": "United States, Texas (fees in USD)", "studio-noir": "Not market-specific", "eleanor-voss": "Not market-specific"}
NUM = {p["slug"]: f"{i+2:02d}" for i, p in enumerate(build.PROJECTS)}   # concept 001 is 01

FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%230d1933'/%3E"
           "%3Cpath d='M9 24V8h15v4H13v3h9v4h-9v5' fill='%23d7fa75'/%3E%3C/svg%3E")

def head(title, desc, base):
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}</title><meta name="description" content="{html.escape(desc)}">'
            f'<link rel="icon" type="image/svg+xml" href="{FAVICON}"><link rel="stylesheet" href="{base}style.css"><link rel="stylesheet" href="{base}ff-work.css"></head>\n<body id="top">\n'
            '<a class="skip" href="#main">Skip to content</a>\n')

def header(base, current=""):
    cur = lambda k: ' aria-current="page"' if current == k else ""
    return ('<header class="wrap navigation">'
            f'<a class="wordmark" href="{base}index.html" aria-label="Form and Flow home">form<span class="amp">&amp;</span>flow</a>'
            '<span class="nav-note">INDEPENDENT DESIGN<br>+ PRACTICAL AUTOMATION</span>'
            f'<nav aria-label="Main navigation"><a href="{base}work/index.html"{cur("work")}>Work</a><a href="{base}index.html#approach">Approach</a>'
            f'<a href="{base}notes/index.html"{cur("notes")}>Notes</a><a href="{base}index.html#contact">Let\u2019s talk <span aria-hidden="true">\u2197</span></a></nav></header>\n')

def foot(base):
    return ('<footer class="wrap"><a class="wordmark" href="' + base + 'index.html">form<span class="amp">&amp;</span>flow</a>'
            '<span>Independent portfolio \u00b7 Working studio name \u00b7 Sample projects are for fictional businesses</span>'
            '<a href="#top">Back to top \u2191</a></footer>\n</body></html>\n')

def index_bar(left, right):
    return f'<div class="wrap section-index"><span>{left}</span><span>{right}</span></div>\n'

def crow(label, inner):
    return f'<section class="wrap case-row"><span class="label">{label}</span><div>{inner}</div></section>\n'

def write(rel, text):
    p = os.path.join(DIST, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8").write(text)

def work_rows(base, concept=True):
    rows = ('<li><a href="' + base + 'index.html#work"><span class="work-no">01</span><span class="work-name">The Enquiry Desk</span>'
            '<p class="work-hard">A working concept: a service page, a short enquiry, and the owner\u2019s view of what arrives.</p><span class="work-kind">Interactive concept</span></a></li>')
    if not concept: rows = ''
    for p in build.PROJECTS:
        rows += (f'<li><a href="{base}work/{p["slug"]}.html"><span class="work-no">{NUM[p["slug"]]}</span><span class="work-name">{p["name"]}</span>'
                 f'<p class="work-hard">{p["hard"]}</p><span class="work-kind">{p["kind"]} \u00b7 sample</span></a></li>')
    return rows

def work_index():
    o = head("Work \u2014 Form & Flow", "One interactive concept and five researched sample builds, each with the reasoning behind it.", "../") + header("../", "work")
    o += '<main id="main">\n<section class="wrap page-head"><h1>Six pieces of work, each argued.</h1>'
    o += '<p>One interactive concept about what happens after an enquiry, and five sample service sites for fictional businesses. Each sample has a live page and a case study covering the research, the decisions, what was left out, and what went wrong.</p></section>\n'
    o += index_bar("SELECTED WORK", "NO CLIENT WORK YET")
    o += f'<div class="wrap"><ul class="work-list">{work_rows("../")}</ul>'
    o += '<p class="note-box">There is no client work here yet, and none is implied. Every sample is for a fictional business and labelled as one. Real projects will be added when they exist, with the client\u2019s permission.</p></div>\n'
    o += '<section class="wrap case-row"><span class="label">How these were built</span><div><ul class="standards">'
    for a, b in [("No invented proof.", "No made-up reviews, ratings, customer counts or logos. If a claim has no source, it is not on the page."),
                 ("Every control works.", "Buttons and links do what they say. No forms that fake a success message."),
                 ("Specific to the business.", "If the name could be swapped for a competitor\u2019s and the page still made sense, it is not finished."),
                 ("Terms stated plainly.", "Price, what is included and excluded, and what happens after contact."),
                 ("Made with AI assistance, stated openly.", "The samples and case studies were made with AI research and coding assistants. Where a claim depends on a source, the source is linked, and anything I could not verify is said so.")]:
        o += f"<li><strong>{a}</strong><span>{b}</span></li>"
    o += '</ul></div></section>\n</main>\n' + foot("../")
    write("work/index.html", o)

def case_page(i, p):
    nxt = build.PROJECTS[(i + 1) % len(build.PROJECTS)]
    o = head(f"{p['name']} \u2014 Form & Flow", p["hard"], "../") + header("../", "work")
    o += '<main id="main">\n' + index_bar(f"WORK / {NUM[p['slug']]}", "SAMPLE BUILD \u00b7 FICTIONAL BUSINESS")
    o += f'<section class="wrap page-head"><h1>{p["h1"]}</h1>'
    facts = list(p["facts"]); facts.insert(2, ("Market", MARKET[p["slug"]]))
    o += '<dl class="facts">' + "".join(f"<div><dt>{a}</dt><dd>{b}</dd></div>" for a, b in facts) + '</dl></section>\n'
    win = (f'<div class="window"><div class="window-bar"><span>Live sample \u00b7 {html.escape(p["name"])}</span><a href="../samples/{p["slug"]}/index.html">Open full page \u2192</a></div>'
           f'<div class="window-body"><iframe src="../samples/{p["slug"]}/index.html" title="Live sample: {html.escape(p["name"])}" loading="lazy"></iframe></div></div>'
           '<p class="window-hint">This is the real page, not a screenshot. Scroll inside it. On a desktop, drag the lower-right corner of the frame to narrow it and watch the layout respond.</p>')
    o += crow("The live sample", win)
    o += crow("The brief", f'<div class="prose"><p>{p["brief"]}</p></div>')
    src = ""
    if p["sources"]:
        src = '<p class="sources">Sources: ' + " \u00b7 ".join(f'<a href="{u}" rel="noopener">{t}</a>' for t, u in p["sources"]) + "</p>"
    o += crow("What I checked first", '<div class="prose">' + "".join(f"<p>{r}</p>" for r in p["research"]) + src + "</div>")
    o += crow("Decisions", '<ul class="decisions">' + "".join(f"<li><b>{a}</b><span>{b}</span></li>" for a, b in p["decisions"]) + "</ul>")
    o += crow("Left out", f'<div class="prose"><p>{p["left"]}</p></div>')
    o += crow("What I would measure", f'<div class="prose"><p>{p["measure"]}</p></div>')
    sw = '<div class="swatches" role="img" aria-label="Palette">' + "".join(f'<i style="background:{c}"></i>' for c in p["swatches"]) + "</div>"
    o += crow("What went wrong or is unfinished", f'<div class="prose"><p>{p["found"]}</p>{sw}</div>')
    o += f'<div class="wrap"><a class="next-project" href="{nxt["slug"]}.html"><span class="label">NEXT PROJECT</span><h2>{nxt["name"]}</h2></a></div>\n</main>\n' + foot("../")
    write(f"work/{p['slug']}.html", o)

def notes():
    o = head("Notes \u2014 Form & Flow", "Short write-ups from researching and building the sample sites.", "../") + header("../", "notes")
    o += '<main id="main">\n<section class="wrap page-head"><h1>Notes.</h1><p>What I learned researching and building the samples. Each note is short, sourced where it makes factual claims, and says what I have not tested.</p></section>\n'
    o += index_bar("WRITTEN 2026", f"{len(build.NOTES)} NOTES")
    o += '<div class="wrap"><ul class="note-list">' + "".join(f'<li><a href="{n["slug"]}.html"><h3>{n["title"]}</h3><p>{n["dek"]}</p></a></li>' for n in build.NOTES) + '</ul></div>\n</main>\n' + foot("../")
    write("notes/index.html", o)
    for n in build.NOTES:
        o = head(f"{n['title']} \u2014 Form & Flow", n["dek"], "../") + header("../", "notes")
        o += '<main id="main">\n' + index_bar('<a href="index.html">\u2190 ALL NOTES</a>', "NOTE")
        o += f'<section class="wrap page-head"><h1>{n["title"]}</h1></section>\n<div class="wrap"><div class="article">{n["body"]}'
        if n["sources"]:
            o += '<p class="sources">Sources: ' + " \u00b7 ".join(f'<a href="{u}" rel="noopener">{t}</a>' for t, u in n["sources"]) + "</p>"
        o += '</div></div>\n</main>\n' + foot("../")
        write(f"notes/{n['slug']}.html", o)

def copy_samples():
    for p in build.PROJECTS:
        src = os.path.join(ROOT, "Final", "sample", p["slug"])
        dst = os.path.join(DIST, "samples", p["slug"])
        if os.path.isdir(dst): shutil.rmtree(dst)
        shutil.copytree(src, dst)
    shutil.copy(os.path.join(ROOT, "ff-work.css"), os.path.join(DIST, "ff-work.css"))

def patch_home():
    path = os.path.join(DIST, "index.html")
    t = open(path, encoding="utf-8").read()
    changed = []
    if 'ff-work.css' not in t:
        t = t.replace('<link rel="stylesheet" href="style.css">', '<link rel="stylesheet" href="style.css"><link rel="stylesheet" href="ff-work.css">', 1); changed.append("css link")
    nav_old = '<a href="#approach">Approach</a><a href="#contact">Let\u2019s talk'
    if 'notes/index.html' not in t and nav_old in t:
        t = t.replace(nav_old, '<a href="#approach">Approach</a><a href="notes/index.html">Notes</a><a href="#contact">Let\u2019s talk', 1); changed.append("nav link")
    sec = ('<section class="wrap more-work" id="more-work" aria-labelledby="more-title">'
           '<div class="section-index"><span>MORE WORK</span><span>SAMPLE BUILDS · FICTIONAL BUSINESSES</span></div>'
           '<div class="section-heading"><h2 id="more-title">Service pages,<br>researched first.</h2>'
           '<p>Five sample sites for fictional businesses, each built from real industry research. Open a live page, or read why it was built that way.</p></div>'
           f'<ul class="work-list">{work_rows("", concept=False)}</ul>'
           '<p class="fine">No client work is shown because there is none yet. <a href="work/index.html">See all work and how it was built</a>.</p></section>\n')
    import re
    m = re.search(r'<section class="wrap more-work".*?</section>\n?', t, re.S)
    if m:
        if m.group(0) != sec: t = t[:m.start()] + sec + t[m.end():]; changed.append("more-work refreshed")
    else:
        marker = '<section id="approach"'
        assert marker in t
        t = t.replace(marker, sec + marker, 1); changed.append("more-work section")
    open(path, "w", encoding="utf-8").write(t)
    return changed

if __name__ == "__main__":
    copy_samples(); work_index()
    for i, p in enumerate(build.PROJECTS): case_page(i, p)
    notes()
    print("patched home:", patch_home() or "already patched")
    print("dist:", DIST)
