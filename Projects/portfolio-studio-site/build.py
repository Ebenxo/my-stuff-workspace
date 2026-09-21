import os, html

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "Drafts")
EMAIL = "ebenezeraaron001@gmail.com"

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700'
         '&family=Instrument+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">')

def head(title, desc, base):
    return (f'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f'<title>{html.escape(title)}</title>\n<meta name="description" content="{html.escape(desc)}">\n'
            f'{FONTS}\n<link rel="stylesheet" href="{base}styles.css">\n</head>\n<body>\n')

def header(base, current=""):
    items = [("work.html", "Work", "work"), ("process.html", "Process", "process"),
             ("notes/index.html", "Notes", "notes"), ("about.html", "About", "about"),
             ("index.html#contact", "Contact", "contact")]
    links = "".join(f'<a href="{base}{h}"' + (' aria-current="page"' if current == k else "") + f'>{t}</a>' for h, t, k in items)
    return ('<header class="site-head"><div class="wrap">'
            f'<a class="mark" href="{base}index.html">form &amp; flow</a>'
            f'<nav class="site-nav" aria-label="Main">{links}</nav>'
            '<span class="status">Open to first client projects</span></div></header>\n')

def foot(base):
    return ('<footer class="site-foot"><div class="wrap"><span>&copy; 2026 Form &amp; Flow. Working studio name. '
            f'Every project shown is a sample for a fictional business.</span><a href="mailto:{EMAIL}">{EMAIL}</a></div></footer>\n</body>\n</html>\n')

def page_title(h1, lede):
    return f'<section class="page-title"><div class="wrap"><h1>{h1}</h1><p>{lede}</p></div></section>\n'

def row(label, inner, rid=""):
    i = f' id="{rid}"' if rid else ""
    return f'<section class="row"{i}><span class="label">{label}</span><div>{inner}</div></section>\n'

# ------------------------------------------------------------------ projects
PROJECTS = [
 dict(slug="halloway", name="Halloway Appliance Repair", kind="Local trade", year="2026",
  hard="A one-truck repair business has to answer price, scope and “is it worth fixing?” before the phone rings.",
  h1="A repair site that answers the fee question before anyone has to call.",
  facts=[("Type","Sample build, fictional business"),("Sector","Residential appliance repair"),("Stack","Plain HTML and CSS, no JavaScript"),("Status","Finished sample, not a client project")],
  brief="A one-technician appliance repair business needs a single page that helps a homeowner with a broken fridge or dryer decide whether to call, and what happens if they do. The business is fictional. The industry facts are not.",
  research=["In the sources I read, diagnostic fees for this trade run about $60–120 and are often credited toward the repair when the customer approves the work. I used $79, credited.",
            "The usual repair-or-replace rule has two conditions: the repair costs more than half a comparable new unit <em>and</em> the appliance is past roughly half its expected life. Cost alone is not the test.",
            "Anyone opening a refrigerant circuit in a residential fridge needs EPA Section 608 certification. Type I covers small appliances, so the technician is listed with that credential rather than a vague “certified expert”."],
  sources=[("Diagnostic fee norms","https://bozmanfix.com/appliance-repair-pricing-transparency/"),("The 50% rule","https://howlongitlasts.com/the-appliance-50-rule-explained/"),("EPA Section 608","https://www.epa.gov/section608/section-608-technician-certification")],
  decisions=[("The fee is on the first screen.","A caller deciding whether to book needs to know what a visit costs, so the fee and the rule for crediting it come first. This is a design choice to test, not a proven result."),
             ("Call and text links, no contact form.","There is no backend, so a form would have to pretend to send. A form that reports success and delivers nothing is worse than no form. <code>tel:</code> and <code>sms:</code> links do exactly what they say."),
             ("A list of what the business will not fix.","Small countertop appliances, commercial equipment, HVAC and new gas lines are excluded and explained. Saying no clearly saves both sides a wasted trip."),
             ("Repair-or-replace is explained with the real rule.","It is the honest answer to “is my 11-year-old washer worth it?”, and it is the page most likely to be read before a decision."),
             ("A condensed, utilitarian typeface in burnt amber and charcoal.","The look is meant to read as equipment labelling and a work van, not a software product.")],
  left="No testimonials, star ratings or “trusted by” strip. They would all be invented, so the section does not exist. No live chat or booking widget either: nothing behind them would work.",
  measure="On a real launch I would count calls and texts that start from the page, how many callers already know the fee, and how many jobs end at the diagnostic stage. I would not promise a lift in any of them beforehand.",
  found="QA turned up a real layout bug: between about 620 and 900 px wide the logo wrapped onto three lines. The stack-to-column breakpoint was too narrow. Fixed and re-checked.",
  swatches=["#f7f4ec","#1c1a17","#c76a1a"], sample="sample/halloway/index.html", stack="Plain HTML and CSS", scope="Single page"),
 dict(slug="kestrel-bend", name="Kestrel Bend Plumbing", kind="Local trade", year="2026",
  hard="A plumbing site that shows what a visit costs, what after-hours costs and what a written quote looks like, and is careful about what it will not claim.",
  h1="A plumber\u2019s page that puts the fee, the after-hours rate and the quote on paper.",
  facts=[("Type","Sample build, fictional company"),("Sector","Residential plumbing, Texas"),("Stack","Plain HTML and CSS, no JavaScript"),("Status","Finished sample, independently checked then fixed")],
  brief="A fictional owner-operated plumbing company north of Austin needs one page that helps a homeowner with a leak or a dead water heater decide whether to call, what it will cost, and what to do in the first minutes of an emergency. The company, the licence holder and the phone number are fictional. The industry facts, price bands and safety wording are researched and sourced.",
  research=["In the sources I read, service-call fees run about $75\u2013150, sometimes credited to an approved repair and sometimes not, and emergency dispatch runs higher. The sample charges $95, credited in full when you approve the work the same visit or return within 14 days. That is the sample firm\u2019s own policy.",
            "After-hours work in the sources runs about 1.5\u20133x the daytime rate. The sample uses 1.5x on weeknights, 2x at weekends and 2.5x on holidays, and says so before anyone calls.",
            "For water heaters, the guides I read use a 50% cost rule plus an age test. The page shows both tests and gives life spans as typical ranges, not promises.",
            "In Texas, the state plumbing board says a Responsible Master Plumber\u2019s licence number \u201cshould be displayed in all advertisements\u201d, and that written estimates and invoices \u201cshould contain\u201d it. The sample uses an obvious placeholder instead of a number that looks real.",
            "On gas, the Wisconsin regulator says to leave the area immediately, call the gas utility\u2019s emergency number or 911 from a safe distance outdoors, and not use phones, lights, appliances, cars, flames or sparks near a suspected leak. The page repeats only that, gives no repair steps, and says the source is another state\u2019s regulator and that readers should check their own utility."],
  sources=[("Service-call and job pricing","https://calljolt.com/blog/plumbing/plumbing-service-call-cost-breakdown"),("Pricing guide","https://www.housecallpro.com/resources/marketing/how-to/how-to-price-plumbing-jobs/"),("Texas plumbing board","https://tsbpe.texas.gov/consumer-information/"),("Wisconsin PSC on gas safety","https://psc.wi.gov/Pages/ServiceType/Energy/PipelineSafety/NaturalGasConsumerSafety.aspx"),("Shutting off the main water valve","https://www.regionalh2o.org/emergency-preparedness/emergency-water-shut")],
  decisions=[("The fee and its credit rule are on the first screen.","A caller weighing a visit needs the fee and the conditions for crediting it. Stating them up front commits the firm to a rule it has to keep."),
             ("A worked quote, weekday and weeknight.","The same job is priced twice with the arithmetic shown: labour, parts and the fee credit. It answers the fear of a running meter and of a surprise total."),
             ("After-hours costs are stated before anyone calls.","The multipliers and the after-hours call fee sit in a table, along with the hours the phone is not answered."),
             ("A refer-out list.","The firm says what it will not do and who should. The list is the sample firm\u2019s own policy; the research behind it was thin."),
             ("Safety text is limited to what a regulator says.","The gas guidance is a short, sourced instruction to leave and call. Steps I could not source, such as frozen pipes or airing out a room, are not on the page."),
             ("A design taken from paperwork.","Verdigris and copper on a pale ground, a slab-serif headline and a left heading rail, so the page reads like an estimate sheet and not a marketing site. No blue drop, no wrench.")],
  left="Testimonials, ratings, photos of people, and the words licensed, insured, bonded, 24/7, free estimate and no hidden fees, none of which a sample can honestly claim. Frozen-pipe and DIY steps. Prices for toilet and faucet replacement, tankless heaters and camera inspections, because the sources ranged too widely to print one number.",
  measure="For a real plumber I would count calls and texts from the page, how many callers already know the fee, and how many after-hours calls go ahead once the multiplier is stated. I would not promise a lift.",
  found="An independent check of the first draft found that it printed a camera-inspection price range from a source I had not been able to read, and a price column labelled \u201cnational\u201d that mixed in a regional range. I removed the first and relabelled the second. The company name was searched only weakly and is not cleared, so the page is marked as a fictional sample and asks search engines not to index it. The licence, insurance and safety wording would need review by a qualified person before a real company used it.",
  swatches=["#f5f6f3","#1c2624","#0b5d57","#9a4419"], sample="sample/kestrel-bend/index.html", stack="Plain HTML and CSS", scope="Single page"),
 dict(slug="marlow-street", name="Marlow Street Dental", kind="Health practice", year="2026",
  hard="A dental site that puts the first-visit price, the X-ray policy and an emergency guide in front of a nervous patient.",
  h1="A dentist’s site that itemises the first visit and knows when to say “go to the ER”.",
  facts=[("Type","Sample build, fictional practice"),("Sector","One-dentist family practice"),("Stack","Plain HTML and CSS, no JavaScript"),("Status","Rebuild of an earlier, weaker version")],
  brief="A one-dentist family practice needs a single page for new patients: what the first visit costs, how insurance works, what to do in an emergency, and what the practice does not treat. The practice, dentist and address are fictional. The fee ranges and clinical guidance are researched.",
  research=["In the sources I read, a new-patient exam without insurance runs about $75–150, bitewing X-rays $25–50, a full-mouth series $100–250 and a cleaning $75–200, and in-house membership plans about $200–400 a year. The sample’s own fees sit inside those ranges and are labelled as sample fees.",
            "ADA/FDA guidance on X-rays is risk-based, not calendar-based: for a low-risk adult, bitewings roughly every two to three years, and more often for someone with a history of decay. The page says so instead of implying every patient is X-rayed every visit.",
            "The ADA describes a knocked-out permanent tooth as time-critical, with the best chance of saving it inside about 30 minutes. Published dental guidance lists swelling, uncontrolled bleeding and severe pain as reasons for urgent care. I added the line that trouble swallowing or breathing means the emergency room, as ordinary safety practice rather than something I sourced to the ADA."],
  sources=[("Dental visit cost ranges","https://www.aflac.com/resources/dental-insurance/how-much-do-dental-x-rays-cost.aspx"),("ADA on dental emergencies","https://www.mouthhealthy.org/all-topics-a-z/dental-emergencies"),("ADA on X-rays","https://www.ada.org/resources/ada-library/oral-health-topics/x-rays-radiographs")],
  decisions=[("The first visit is a table with a total.","Exam $95, X-rays $55, cleaning $115, $265 typical. A nervous patient who can see the number can decide whether to call. I did not survey other practices, so I make no claim about what they publish."),
             ("The page explains how X-ray decisions are made.","A patient who worries about being over-X-rayed is asking how the practice decides. Saying “not on a calendar” answers that, and it matches the risk-based guidance."),
             ("An emergency guide that sends people elsewhere when needed.","Red is used once on the page, for this block only. The guide tells the reader when the right call is the emergency room, not the practice."),
             ("The membership section says when not to join.","It costs $299 and pays back if you would visit twice. If you would come once, the page says do not buy it. That sentence is the trust signal."),
             ("Booking by phone or text only.","There is no backend, so no form. The links open the phone or messages app and do exactly what the button says.")],
  left="No patient reviews, star rating, patient count or “trusted by families” claim. No emoji icons. No online booking widget. No before-and-after photos.",
  measure="On a real launch I would count first-visit calls and texts from the page, how many mention the fee, and how many emergency callers are told to go elsewhere. I would not promise a lift.",
  found="The first version of this sample was worse. It claimed a 4.9/5 rating, 1,200+ patients seen and “70% less radiation”, none of which was true or sourced, and used emoji as icons. It failed my own standards, so I replaced it rather than edit it. The old version is still in the project history.",
  swatches=["#f4f6f2","#16241f","#0e5a55","#8c2f1b"], sample="sample/marlow-street/index.html", stack="Plain HTML and CSS", scope="Single page"),
 dict(slug="studio-noir", name="Studio Noir", kind="Creative portfolio", year="2026",
  hard="A portfolio grid that stays a plain, fast grid, and a detail page that can be reused for every new project.",
  h1="A portfolio that is a grid, a template and nothing else.",
  facts=[("Type","Sample build, fictional persona"),("Sector","Independent designer"),("Stack","Plain HTML and CSS, three pages"),("Status","Finished sample, placeholder imagery")],
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
  swatches=["#faf9f6","#1a1a1a","#c8553d"], sample="sample/studio-noir/index.html", stack="Plain HTML and CSS", scope="Three pages"),
 dict(slug="eleanor-voss", name="Eleanor Voss", kind="Personal bio page", year="2026",
  hard="One quiet page in serif type that has to survive being extended later without a rebuild.",
  h1="One page, set in serif, built to grow downward.",
  facts=[("Type","Sample build, fictional person"),("Sector","Independent editor"),("Stack","Plain HTML and CSS, one page"),("Status","Finished sample, English placeholder copy")],
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
  swatches=["#f4f2ec","#2b2a26","#3d4a5c"], sample="sample/eleanor-voss/index.html", stack="Plain HTML and CSS", scope="One page"),
]

NOTES = [
 dict(slug="price-first-screen", title="Put the price where the caller looks first",
  dek="Two trades, two researched sites, and the same conclusion about the fee.",
  body="""<p class="lead">When I researched appliance repair and family dentistry for two sample sites, the sources I read agreed on a price range but did not tell a customer what any one business charges. I did not survey enough company sites to say how common it is to leave the price off.</p>
<h2>What the numbers look like</h2>
<p>In the sources I read, appliance repair diagnostic fees run about $60–120, and many shops credit the fee toward the repair if you approve the work. A new dental patient without insurance can expect roughly $75–150 for an exam, $25–50 for bitewing X-rays and $75–200 for a cleaning. Neither trade has one price; both have a normal range. A customer who does not know the range may assume the worst.</p>
<h2>What I did with it</h2>
<p>On the repair site the fee is on the first screen: $79, credited if you approve the repair. On the dental site the first visit is a table with a total of $265, and a note that a cleaning may be swapped for a different treatment if the exam shows gum disease. In both cases the price comes with the rule that decides when it changes. A bare number with no conditions would be a promise the business might not keep.</p>
<h2>When this does not work</h2>
<p>Some businesses cannot quote before seeing the job: a roofer, a kitchen fitter. The answer there is not to hide the price. It is to say what it depends on, give a realistic starting point if one exists, and explain what happens at the quoting visit. “Contact us for a quote” with nothing else is the version I would not ship.</p>
<h2>What I have not measured</h2>
<p>I have not tested whether a visible fee produces more calls. These are sample builds with no traffic. The claim is narrower: stating the fee forces a business to decide what it is, and it gives a caller something concrete to weigh before phoning.</p>""",
  sources=[("Appliance repair diagnostic fees","https://bozmanfix.com/appliance-repair-pricing-transparency/"),("Dental visit costs without insurance","https://www.aflac.com/resources/dental-insurance/how-much-do-dental-x-rays-cost.aspx")]),
 dict(slug="writing-for-pain", title="Writing for the person in pain",
  dek="What changed when I wrote a dentist’s emergency guide from the ADA’s own guidance.",
  body="""<p class="lead">An emergency section on a dentist’s site is read by someone whose face hurts and who is deciding, right now, whether to call, wait, or go to hospital. That reader needs a decision, not reassurance.</p>
<h2>Separate “call now” from “go to hospital”</h2>
<p>Published dental guidance, including the ADA’s, lists a knocked-out permanent tooth, facial swelling, uncontrolled bleeding and severe pain as reasons for urgent care. Trouble swallowing or breathing, or a serious jaw or face injury, sends you to the emergency room. That last step is ordinary safety practice and I added it myself; I did not source it to the ADA. A dentist’s page that pulls everything toward the practice is wrong for some readers. The sample says plainly when the right call is the emergency room, and it is the only place on the page that uses red.</p>
<h2>The numbered list earns its numbers</h2>
<p>The knocked-out-tooth instructions are numbered because the order is real: pick it up by the crown, place it back if you can or keep it moist, then call. The ADA says the tooth has the best chance within about 30 minutes, so that figure is stated once, at the top of the list.</p>
<h2>Say what you will not diagnose</h2>
<p>The section ends with a plain line: this is general information, not a diagnosis, and a mild toothache with no swelling or fever can usually wait for an appointment. Saying what is <em>not</em> an emergency is as useful as listing what is.</p>
<h2>What is still fictional</h2>
<p>The practice, the dentist and the same-day slot policy are invented for the sample. A real practice would need its own protocol and a clinician to review every sentence of this section before it goes live.</p>""",
  sources=[("ADA MouthHealthy: dental emergencies","https://www.mouthhealthy.org/all-topics-a-z/dental-emergencies"),("Cleveland Clinic: dental emergencies","https://my.clevelandclinic.org/health/articles/11368--dental-emergencies-what-to-do")]),
 dict(slug="buttons-that-work", title="A button should do what it says",
  dek="Why the sample sites use phone and text links instead of contact forms.",
  body="""<p class="lead">Every sample on this site is a static page with no server behind it. That rules out a working contact form, and it is the reason none of them has one.</p>
<h2>The fake form problem</h2>
<p>A form on a static page can show a “Thanks, we will be in touch” message, but nothing has been sent. The visitor leaves believing they have contacted the business. On a real client site that is a lost enquiry and, worse, a lost enquiry the business does not know it lost.</p>
<h2>What works without a backend</h2>
<p><code>tel:</code> opens the phone dialler. <code>sms:</code> opens the messages app. <code>mailto:</code> opens the email app. Each does exactly what its label says, needs no service to run, and cannot silently fail. For a repair shop or a dentist, where the customer usually wants to speak to someone anyway, a large phone button is the better control.</p>
<h2>When a form is right</h2>
<p>A form earns its place when it has a real destination: an inbox, a booking system, a spreadsheet, with a confirmation that is only shown after delivery succeeds, and an error message that tells the visitor what to do if it does not. Then it is a small piece of engineering, and it should be quoted as one.</p>
<h2>The rule I use</h2>
<p>If a control is on the page, pressing it must do what it promises or the page must say plainly that it is a demonstration. Otherwise the control is not shipped.</p>""",
  sources=[]),
]

# ------------------------------------------------------------------ builders
def case_page(i, p):
    nxt = PROJECTS[(i + 1) % len(PROJECTS)]
    o = head(f"{p['name']} — form & flow", p["hard"], "../") + header("../", "work")
    o += '<main>\n<section class="case-head"><div class="wrap">\n<a class="back" href="../work.html">&larr; All work</a>\n'
    o += f'<h1>{p["h1"]}</h1>\n<dl class="facts">' + "".join(f"<div><dt>{a}</dt><dd>{b}</dd></div>" for a, b in p["facts"]) + '</dl>\n</div></section>\n<div class="wrap">\n'
    win = (f'<div class="window"><div class="window-bar"><span>Live sample &middot; {html.escape(p["name"])}</span>'
           f'<a href="../{p["sample"]}">Open full page &rarr;</a></div>'
           f'<div class="window-body"><iframe src="../{p["sample"]}" title="Live sample: {html.escape(p["name"])}" loading="lazy"></iframe></div></div>'
           '<p class="window-hint">This is the real page, not a screenshot. Scroll inside it. On a desktop, drag the lower-right corner of the frame to narrow it and watch the layout respond.</p>')
    o += row("The live sample", win)
    o += row("The brief", f'<div class="prose"><p>{p["brief"]}</p></div>')
    src = ""
    if p["sources"]:
        src = '<p class="sources">Sources: ' + " &middot; ".join(f'<a href="{u}" rel="noopener">{t}</a>' for t, u in p["sources"]) + "</p>"
    o += row("What I checked first", '<div class="prose">' + "".join(f"<p>{r}</p>" for r in p["research"]) + src + "</div>")
    o += row("Decisions", '<ul class="decisions">' + "".join(f"<li><b>{a}</b><span>{b}</span></li>" for a, b in p["decisions"]) + "</ul>")
    o += row("Left out", f'<div class="prose"><p>{p["left"]}</p></div>')
    o += row("What I would measure", f'<div class="prose"><p>{p["measure"]}</p></div>')
    sw = '<div class="swatches" role="img" aria-label="Palette">' + "".join(f'<i style="background:{c}"></i>' for c in p["swatches"]) + "</div>"
    o += row("What went wrong or is unfinished", f'<div class="prose"><p>{p["found"]}</p>{sw}</div>')
    o += f'</div>\n<div class="wrap"><a class="next" href="{nxt["slug"]}.html"><span class="label">Next project</span><h2>{nxt["name"]}</h2></a></div>\n</main>\n' + foot("../")
    return o

def work_page():
    o = head("Work — form & flow", "Four sample builds for fictional small businesses, each with its research, decisions and limits.", "") + header("", "work")
    o += '<main>\n' + page_title("Four projects, each argued.", "Every project here is a sample for a fictional business, built to show method. Each has a live page you can use and a case study that says what I researched, decided, left out, and got wrong.")
    o += '<div class="wrap">\n'
    for p in PROJECTS:
        d = (f'<h2>{p["name"]}</h2><p class="prose" style="color:var(--ink-2)">{p["hard"]}</p><dl>'
             f'<dt>Scope</dt><dd>{p["scope"]}</dd><dt>Stack</dt><dd>{p["stack"]}</dd><dt>Status</dt><dd>{p["facts"][3][1]}</dd></dl>'
             f'<div class="actions"><a class="btn" href="case/{p["slug"]}.html">Read the case study</a>'
             f'<a class="btn ghost" href="{p["sample"]}">Open the live page</a></div>')
        o += f'<article class="project"><span class="label kind">{p["kind"]} &middot; {p["year"]}</span><div>{d}</div></article>\n'
    o += '<p class="note" style="margin-block:2.5rem">No client work is shown because there is none yet. When there is, it will be added here with the client’s permission, and the samples will stay labelled as samples.</p>\n</div>\n</main>\n' + foot("")
    return o

def process_page():
    o = head("Process — form & flow", "How a project runs: what to bring, what happens, what is included, and what I will say no to.", "") + header("", "process")
    o += '<main>\n' + page_title("How a project runs.", "Scoped first and priced after. Here is the sequence, what I need from you, and where the edges are.")
    o += '<div class="wrap">\n'
    o += row("Before we talk", '<h2>What is useful to have</h2><ul class="checklist">'
             '<li><strong>What the business does,</strong> in a sentence a customer would use.</li>'
             '<li><strong>The one thing the page should make happen:</strong> a call, a booking, a quote request.</li>'
             '<li><strong>Anything that already exists:</strong> current site, logo, photos, price list, opening hours.</li>'
             '<li><strong>Your real constraints:</strong> deadline, budget range, who signs off.</li></ul>'
             '<p class="prose" style="color:var(--ink-2)">None of this has to be tidy. A voice note or a few bullet points is enough to start.</p>')
    o += row("The sequence", '<h2>Four stages</h2><dl class="stages">'
             '<dt>1. Scoping conversation</dt><dd>We agree the purpose, the audience, what is in and out of scope, and what you need to supply. Price and timing are agreed here, not before.</dd>'
             '<dt>2. Research and first draft</dt><dd>I look at how your trade or field works: what customers ask, what competitors hide, what is regulated. Then I build a first version you can open on your own phone.</dd>'
             '<dt>3. One round of changes, then checks</dt><dd>You send changes in one batch. I make them and then test on phone and desktop, with keyboard navigation, and for text contrast.</dd>'
             '<dt>4. Handover</dt><dd>You receive the files and a short guide to editing text and swapping images. Your domain and hosting stay in your name.</dd></dl>')
    o += row("Included and not", '<h2>The edges</h2><div class="prose">'
             '<p><strong>Included in a project:</strong> the agreed pages, mobile and desktop layout, contact links that work, basic on-page details (titles, descriptions, alt text), the round of changes, and the handover guide.</p>'
             '<p><strong>Separate and agreed at scoping:</strong> copywriting or rewriting, photography, logo work, forms that connect to a real inbox or booking tool, domain and hosting fees, and any ongoing updates.</p>'
             '<p><strong>Not something I sell:</strong> guaranteed search rankings or traffic, fake reviews, invented statistics, and hidden terms.</p></div>')
    o += row("Cost", '<h2>Price follows scoping</h2><div class="prose"><p>I do not publish a price list, because one page with your content ready and one page that needs research, writing and a booking integration are different jobs. What moves the price: number of pages, whether copy and images exist, whether a working form or booking tool is needed, and how much research the field needs. You get a written scope and a fixed price for that scope before I start.</p></div>')
    o += row("Start", '<h2>How to begin</h2><div class="prose"><p>Send an email with what the business does and what you want the page to do. I reply with questions, not a pitch.</p></div>'
             f'<div class="actions"><a class="btn" href="mailto:{EMAIL}">Email {EMAIL}</a></div>')
    o += '</div>\n</main>\n' + foot("")
    return o

def about_page():
    o = head("About — form & flow", "Who is behind Form & Flow, how the work is made, and where things honestly stand.", "") + header("", "about")
    o += '<main>\n' + page_title("One person, early in the work, and honest about it.", "Form &amp; Flow is a working name for a small studio that builds websites for small businesses.")
    o += '<div class="wrap">\n'
    o += row("Where things stand", '<div class="prose"><p>The portfolio holds four sample builds for fictional businesses. There are no client projects yet, and nothing on this site implies otherwise. I am taking on first projects.</p><p>I would rather show four pieces of work I can defend line by line than a long list I cannot.</p></div>')
    o += row("What I make", '<div class="prose"><p>Landing pages and small sites for businesses that sell a service: repair, health, trades, independent professionals. Each starts with research into how that business actually works, and ends with a page that could not be reskinned for a competitor.</p><p>The HTML and CSS are plain, with no page builders or frameworks, so the result loads quickly and is easy to hand over.</p></div>')
    o += row("How the work is made", '<div class="prose"><p>I use AI coding assistants for research and drafting, and I check the results myself: in a browser, at phone width, for contrast and keyboard use, and against the standards on the home page. Where a claim comes from research, the case study links the source. Where I could not check something, it says so.</p></div>')
    o += row("Standards", '<div class="prose"><p>No invented reviews, ratings, customer counts or logos. No buttons that do nothing. No page that would fit any business. No hidden terms. The reasoning is in the <a href="notes/index.html">notes</a>.</p></div>')
    o += row("Contact", f'<div class="prose"><p>The best way to reach me is email.</p></div><div class="actions"><a class="btn" href="mailto:{EMAIL}">{EMAIL}</a></div>')
    o += '</div>\n</main>\n' + foot("")
    return o

def notes_index():
    o = head("Notes — form & flow", "Short write-ups from researching and building the samples.", "../") + header("../", "notes")
    o += '<main>\n' + page_title("Notes.", "What I learned researching and building the samples. Each note is short, sourced where it makes factual claims, and says what I have not tested.")
    o += '<div class="wrap"><section class="row"><span class="label">Written 2026</span><ul class="note-list">'
    for n in NOTES:
        o += f'<li><a href="{n["slug"]}.html"><h3>{n["title"]}</h3><p>{n["dek"]}</p></a></li>'
    o += '</ul></section></div>\n</main>\n' + foot("../")
    return o

def note_page(n):
    o = head(f"{n['title']} — form & flow", n["dek"], "../") + header("../", "notes")
    o += f'<main>\n<section class="case-head"><div class="wrap"><a class="back" href="index.html">&larr; All notes</a><h1>{n["title"]}</h1></div></section>\n'
    o += '<div class="wrap"><section class="row"><span class="label">Note</span><div class="article">' + n["body"]
    if n["sources"]:
        o += '<p class="sources">Sources: ' + " &middot; ".join(f'<a href="{u}" rel="noopener">{t}</a>' for t, u in n["sources"]) + "</p>"
    o += '</div></section></div>\n</main>\n' + foot("../")
    return o

def index_page():
    o = head("form & flow — websites for small businesses", "A working studio for small-business websites. Four sample builds, each explained: the research, the decisions, and what is unfinished.", "") + header("", "")
    o += '<main>\n<section class="hero"><div class="wrap">\n'
    o += '<h1>Small-business websites that say what the business actually does.</h1>\n'
    o += '<p class="lede">I research the trade first, then build the page around the questions customers ask before they call. Below are four sample builds, each one a live page you can use and a case study that shows the reasoning.</p>\n'
    o += '<div class="actions"><a class="btn" href="work.html">See the work</a><a class="btn ghost" href="process.html">How a project runs</a></div>\n</div></section>\n<div class="wrap">\n'
    items = "".join(f'<li class="work-item"><a href="case/{p["slug"]}.html"><h3>{p["name"]}</h3><span class="kind">{p["kind"]} &middot; {p["year"]}</span><p class="hard">{p["hard"]}</p></a></li>' for p in PROJECTS)
    o += row("Selected work", f'<ul class="work-list">{items}</ul><p class="note">All four are sample builds for fictional businesses, made to show method. There is no client work here yet, and none is implied.</p>', "work")
    nl = "".join(f'<li><a href="notes/{n["slug"]}.html"><h3>{n["title"]}</h3><p>{n["dek"]}</p></a></li>' for n in NOTES)
    o += row("Notes", f'<ul class="note-list">{nl}</ul>', "notes")
    rules = "".join(f"<li><strong>{a}</strong><span>{b}</span></li>" for a, b in [
        ("Invented proof.","No made-up reviews, ratings, customer counts or logos. If a claim has no source, it is not on the page."),
        ("Buttons that do nothing.","Every control either works or is not there. No forms that fake a success message."),
        ("A page that fits any business.","If the name could be swapped for a competitor’s and the page still made sense, it is not finished."),
        ("Hidden terms.","Price, what is included, what is excluded, and what happens after you get in touch are stated plainly.")])
    o += row("Standards", f'<h2>What I will not ship</h2><ul class="rules">{rules}</ul>', "standards")
    o += row("Contact", '<h2>Have a real project?</h2><div class="prose"><p>Tell me what the business does and what you want the page to do. I will reply with questions, not a sales pitch.</p></div>'
             f'<div class="actions"><a class="btn" href="mailto:{EMAIL}">Email {EMAIL}</a><a class="btn ghost" href="process.html">How a project runs</a></div>', "contact")
    o += '</div>\n</main>\n' + foot("")
    return o

def write(rel, text):
    path = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(text)

if __name__ == "__main__":
    write("index.html", index_page())
    write("work.html", work_page())
    write("process.html", process_page())
    write("about.html", about_page())
    write("notes/index.html", notes_index())
    for n in NOTES: write(f"notes/{n['slug']}.html", note_page(n))
    for i, p in enumerate(PROJECTS): write(f"case/{p['slug']}.html", case_page(i, p))
    print("built", 4 + 1 + len(NOTES) + len(PROJECTS), "pages")
