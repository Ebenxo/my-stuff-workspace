import os, html

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "Drafts")
EMAIL = "ebenezeraaron001@gmail.com"

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700'
         '&family=Instrument+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">')

def head(title, desc, css):
    return (f'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f'<title>{html.escape(title)}</title>\n<meta name="description" content="{html.escape(desc)}">\n'
            f'{FONTS}\n<link rel="stylesheet" href="{css}">\n</head>\n<body>\n')

def header(base, current=""):
    def a(href, text, key):
        cur = ' aria-current="page"' if current == key else ""
        return f'<a href="{base}{href}"{cur}>{text}</a>'
    return ('<header class="site-head"><div class="wrap">'
            f'<a class="mark" href="{base}index.html">form &amp; flow</a>'
            f'<nav class="site-nav" aria-label="Main">{a("index.html#work","Work","work")}'
            f'{a("index.html#standards","Standards","s")}{a("index.html#process","Process","p")}'
            f'{a("index.html#contact","Contact","c")}</nav>'
            '<span class="status">Open to first client projects</span></div></header>\n')

FOOT = ('<footer class="site-foot"><div class="wrap"><span>&copy; 2026 Form &amp; Flow. Working studio name.</span>'
        f'<a href="mailto:{EMAIL}">{EMAIL}</a></div></footer>\n</body>\n</html>\n')

PROJECTS = [
 dict(slug="halloway", name="Halloway Appliance Repair", kind="Local trade", year="2026",
  hard="A one-truck repair business has to answer price, scope and “is it worth fixing?” before the phone rings.",
  title="Halloway Appliance Repair",
  h1="A repair site that answers the fee question before anyone has to call.",
  facts=[("Type","Sample build, fictional business"),("Sector","Residential appliance repair"),("Stack","Hand-written HTML and CSS, no JavaScript"),("Status","Finished sample, not a client project")],
  brief="A one-technician appliance repair business needs a single page that helps a homeowner with a broken fridge or dryer decide whether to call, and what happens if they do. The business is fictional. The industry facts are not.",
  research=["Diagnostic fees in this trade commonly run $60–120 and are credited toward the repair when the customer approves the work. I used $79, credited.",
            "The usual repair-or-replace rule has two conditions: the repair costs more than half a comparable new unit <em>and</em> the appliance is past roughly half its expected life. Cost alone is not the test.",
            "Anyone opening a refrigerant circuit in a residential fridge needs EPA Section 608 certification. Type I covers small appliances, so the technician is listed with that credential rather than a vague “certified expert”."],
  sources=[("Diagnostic fee norms","https://bozmanfix.com/appliance-repair-pricing-transparency/"),("The 50% rule","https://howlongitlasts.com/the-appliance-50-rule-explained/"),("EPA Section 608","https://www.epa.gov/section608/section-608-technician-certification")],
  decisions=[("The fee is on the first screen.","It is the objection callers raise first, and competitors tend to bury it. Stating $79 and when it is credited up front filters out the wrong calls."),
             ("Call and text links, no contact form.","There is no backend, so a form would have to pretend to send. A form that reports success and delivers nothing is worse than no form. <code>tel:</code> and <code>sms:</code> links do exactly what they say."),
             ("A list of what the business will not fix.","Small countertop appliances, commercial equipment, HVAC and new gas lines are excluded and explained. Saying no clearly saves both sides a wasted trip."),
             ("Repair-or-replace is explained with the real rule.","It is the honest answer to “is my 11-year-old washer worth it?”, and it is the page most likely to be read before a decision."),
             ("A condensed, utilitarian typeface in burnt amber and charcoal.","The look is meant to read as equipment labelling and a work van, not a software product.")],
  left="No testimonials, star ratings or “trusted by” strip. They would all be invented, so the section does not exist. No live chat or booking widget either: nothing behind them would work.",
  measure="On a real launch I would count calls and texts that start from the page, how many callers already know the fee, and how many jobs end at the diagnostic stage. I would not promise a lift in any of them beforehand.",
  found="QA turned up a real layout bug: between about 620 and 900 px wide the logo wrapped onto three lines. The stack-to-column breakpoint was too narrow. Fixed and re-checked.",
  swatches=["#f7f4ec","#1c1a17","#c76a1a"], sample="sample/halloway/index.html"),
 dict(slug="studio-noir", name="Studio Noir", kind="Creative portfolio", year="2026",
  hard="A portfolio grid that stays a plain, fast grid, and a detail page that can be reused for every new project.",
  title="Studio Noir",
  h1="A portfolio that is a grid, a template and nothing else.",
  facts=[("Type","Sample build, fictional persona"),("Sector","Independent designer"),("Stack","Hand-written HTML and CSS, three pages"),("Status","Finished sample, placeholder imagery")],
  brief="Two live job briefs asked for the same thing: a clean portfolio where the work leads, an even grid with no sliders or masonry, and pages the owner can extend later without a developer. Studio Noir is a sample built to that spec for a fictional designer.",
  research=["Both briefs ruled out sliders and masonry and asked for plain HTML and CSS, so the structure is three static pages: an intro, a work grid, and one reusable project page.",
            "The grid collapses from three columns to two to one at set widths. Every thumbnail shares one aspect ratio so rows stay aligned."],
  sources=[],
  decisions=[("An even grid, on purpose.","Unequal masonry tiles imply the projects are ranked by size. A uniform grid lets the titles and the work do the ranking."),
             ("One project template, not one page per project.","Adding a project means duplicating a file and swapping the content. It is the answer to “easy for me to update later”."),
             ("One accent colour on a neutral ground.","A portfolio’s job is to frame someone else’s work, so the site stays quiet."),
             ("Gradient blocks instead of stock photos.","Stock imagery would add licensing questions and imply work that does not exist.")],
  left="Filters, a lightbox and animated transitions. None of them help a visitor decide to get in touch.",
  measure="For a real portfolio the test is whether a visitor reaches a project page and then the contact link. Load time on a mid-range phone matters more than any effect.",
  found="Honest limitation: a portfolio lives or dies on its real imagery, and this sample has none. The structure is finished; the content is a stand-in.",
  swatches=["#faf9f6","#1a1a1a","#c8553d"], sample="sample/studio-noir/index.html"),
 dict(slug="eleanor-voss", name="Eleanor Voss", kind="Personal bio page", year="2026",
  hard="One quiet page in serif type that has to survive being extended later without a rebuild.",
  title="Eleanor Voss",
  h1="One page, set in serif, built to grow downward.",
  facts=[("Type","Sample build, fictional person"),("Sector","Independent editor"),("Stack","Hand-written HTML and CSS, one page"),("Status","Finished sample, English placeholder copy")],
  brief="A live brief asked for a small, classic personal bio page: clean serif type, a muted resume-style palette, one portrait, simple contact links, and a layout that can take work experience and a portfolio later. Eleanor Voss is a fictional sample of that.",
  research=["The brief’s acceptance criteria were specific: load in under 3 seconds on 4G, pass WCAG AA contrast, render correctly on phone, tablet and desktop. The page is a static file with one web font, which is why load time is a fair thing to promise.",
            "Body text is #5c5a52 on #f4f2ec, about 5.9:1, above the 4.5:1 AA threshold for normal text."],
  sources=[],
  decisions=[("Serif for everything readable, sans only for labels.","It gives the resume feel the brief described without decoration."),
             ("Sections stack downward with a fixed label style.","A new section is a copy-and-paste block, so the page grows without a redesign."),
             ("The copy stays in English.","The real client wants their own text, in their own language. It is theirs to supply, and inventing it for a sample would be presumptuous.")],
  left="Animation, a dark mode toggle and social-feed embeds. A bio page is read once and needs to be legible.",
  measure="The 3-second load criterion is the one to verify on a real connection. I have not measured it for this sample, so I am not claiming it.",
  found="The portrait is a gradient block. Any real photo needs sizing and an alt text written for that specific person.",
  swatches=["#f4f2ec","#2b2a26","#3d4a5c"], sample="sample/eleanor-voss/index.html"),
]

def case_page(i, p):
    nxt = PROJECTS[(i + 1) % len(PROJECTS)]
    out = head(f"{p['title']} — form & flow", p["hard"], "../styles.css")
    out += header("../")
    out += '<main>\n<section class="case-head"><div class="wrap">\n'
    out += '<a class="back" href="../index.html#work">&larr; All work</a>\n'
    out += f'<h1>{p["h1"]}</h1>\n<dl class="facts">'
    out += "".join(f"<div><dt>{a}</dt><dd>{b}</dd></div>" for a, b in p["facts"])
    out += '</dl>\n</div></section>\n<div class="wrap">\n'
    out += f'<section class="row"><span class="label">The brief</span><div class="prose"><p>{p["brief"]}</p></div></section>\n'
    out += '<section class="row"><span class="label">What I checked first</span><div class="prose">'
    out += "".join(f"<p>{r}</p>" for r in p["research"])
    if p["sources"]:
        out += '<p class="sources">Sources: ' + " &middot; ".join(f'<a href="{u}" rel="noopener">{t}</a>' for t, u in p["sources"]) + "</p>"
    out += "</div></section>\n"
    out += '<section class="row"><span class="label">Decisions</span><ul class="decisions">'
    out += "".join(f"<li><b>{a}</b><span>{b}</span></li>" for a, b in p["decisions"])
    out += "</ul></section>\n"
    out += f'<section class="row"><span class="label">Left out</span><div class="prose"><p>{p["left"]}</p></div></section>\n'
    out += f'<section class="row"><span class="label">What I would measure</span><div class="prose"><p>{p["measure"]}</p></div></section>\n'
    out += f'<section class="row"><span class="label">What went wrong or is unfinished</span><div class="prose"><p>{p["found"]}</p>'
    out += '<div class="swatches" role="img" aria-label="Palette">' + "".join(f'<i style="background:{c}"></i>' for c in p["swatches"]) + "</div>"
    out += f'<div class="actions"><a class="btn" href="../{p["sample"]}">Open the live sample</a></div></div></section>\n'
    out += '</div>\n'
    out += f'<div class="wrap"><a class="next" href="{nxt["slug"]}.html"><span class="label">Next</span><h2>{nxt["name"]}</h2></a></div>\n'
    out += "</main>\n" + FOOT
    return out

def index_page():
    out = head("form & flow — websites for small businesses", "A working studio for small-business websites. Three sample builds, each explained: the research, the decisions, and what is unfinished.", "styles.css")
    out += header("")
    out += '<main>\n<section class="hero"><div class="wrap">\n'
    out += '<h1>Small-business websites that say what the business actually does.</h1>\n'
    out += '<p class="lede">I research the trade first, then build the page around the questions customers ask before they call. Below are three sample builds and the reasoning behind each.</p>\n'
    out += '</div></section>\n<div class="wrap">\n'
    out += '<section class="row" id="work"><span class="label">Selected work</span><div><ul class="work-list">'
    for p in PROJECTS:
        out += (f'<li class="work-item"><a href="case/{p["slug"]}.html"><h3>{p["name"]}</h3>'
                f'<span class="kind">{p["kind"]} &middot; {p["year"]}</span><p class="hard">{p["hard"]}</p></a></li>')
    out += '</ul>\n<p class="note">All three are sample builds for fictional businesses, made to show method. There is no client work here yet, and none is implied. Real projects will be added as they exist.</p></div></section>\n'
    out += '<section class="row" id="standards"><span class="label">Standards</span><div><h2>What I will not ship</h2><ul class="rules">'
    for a, b in [("Invented proof.","No made-up reviews, ratings, customer counts or logos. If a claim has no source, it is not on the page."),
                 ("Buttons that do nothing.","Every control either works or is not there. No forms that fake a success message."),
                 ("A page that fits any business.","If the name could be swapped for a competitor’s and the page still made sense, it is not finished."),
                 ("Hidden terms.","Price, what is included, what is excluded, and what happens after you get in touch are stated plainly.")]:
        out += f"<li><strong>{a}</strong><span>{b}</span></li>"
    out += '</ul></div></section>\n'
    out += '<section class="row" id="process"><span class="label">How a project runs</span><div><h2>Scoped first, priced after.</h2><dl class="stages">'
    for a, b in [("A short conversation","We agree what the page must do, who it is for, and what you already have: copy, photos, a domain. Nothing is priced before this."),
                 ("Research and a first draft","I look at how your trade actually works and what customers ask, then build a first version you can see and react to."),
                 ("Revision and checks","One agreed round of changes, then testing on phone and desktop, contrast and keyboard use."),
                 ("Handover","You get the files and a short guide to changing text and images. Hosting and any paid tools are separate and stay in your name.")]:
        out += f"<dt>{a}</dt><dd>{b}</dd>"
    out += '</dl></div></section>\n'
    out += ('<section class="row" id="contact"><span class="label">Contact</span><div><h2>Have a real project?</h2>'
            '<div class="prose"><p>Tell me what the business does and what you want the page to do. I will reply with questions, not a sales pitch.</p></div>'
            f'<div class="actions"><a class="btn" href="mailto:{EMAIL}">Email {EMAIL}</a></div></div></section>\n')
    out += '</div>\n</main>\n' + FOOT
    return out

os.makedirs(os.path.join(OUT, "case"), exist_ok=True)
open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(index_page())
for i, p in enumerate(PROJECTS):
    open(os.path.join(OUT, "case", p["slug"] + ".html"), "w", encoding="utf-8").write(case_page(i, p))
print("built", 1 + len(PROJECTS), "pages")
