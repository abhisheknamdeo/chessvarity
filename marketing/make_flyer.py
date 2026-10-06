"""Build marketing/flyer.html (two A5 flyers on one landscape A4) and render it to marketing/flyer.pdf and flyer.png."""
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent            # marketing/: qr.svg lives here
ROOT = HERE.parent

logo = (ROOT / "src/chesscoach/static/logo.svg").read_text(encoding="utf-8")
logo = re.sub(r"<title>.*?</title>", "", logo)
logo = logo.replace('id="gold"', 'id="gold-{n}"').replace("url(#gold)", "url(#gold-{n})")
qr = (HERE / "qr.svg").read_text(encoding="utf-8").replace("<svg ", '<svg shape-rendering="crispEdges" ')

# The app's own icons (static/js/dom.js), drawn as white strokes.
ICONS = {
    "trophy": "M8 21h8M12 17v4M7 4h10v5a5 5 0 01-10 0V4zM17 5h3v2a3 3 0 01-3 3M7 5H4v2a3 3 0 003 3",
    "camera": "M4 7h3l2-3h6l2 3h3a1 1 0 011 1v11a1 1 0 01-1 1H4a1 1 0 01-1-1V8a1 1 0 011-1zM12 17a4 4 0 100-8 4 4 0 000 8z",
    "target": "M12 21a9 9 0 100-18 9 9 0 000 18zM12 16a4 4 0 100-8 4 4 0 000 8zM12 12h.01",
    "chart": "M3 3v18h18M7 15l4-4 3 3 5-6",
    "calendar": "M3 5h18v16H3zM3 10h18M8 3v4M16 3v4",
    "message": "M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z",
}

# (icon, colour, title, text). Every claim here is something the app does today.
FEATURES = [
    ("trophy", "#2748c7", "Your USCF record, done for you",
     "Type your USCF ID once. Every tournament, round, opponent and result appears by itself, with your rating journey and a month-by-month scorecard."),
    ("camera", "#0d9488", "Snap it. Upload it. Learn from it.",
     "Upload a PGN or tap in the moves, and keep a photo of your scoresheet with the game. Then see every move reviewed."),
    ("target", "#e0533d", "Catch the mistake you keep making",
     "We study all your games together to find the habits costing you points, and show you exactly where they happened."),
    ("chart", "#7c3aed", "A coach’s plan, built from your games",
     "Know your top 3 priorities, your next rating milestone and what to train each day of the week."),
    ("calendar", "#d97706", "Tournament weekends, sorted",
     "Registration, fees, hotel and travel tracked for every event, and all your past and upcoming games in one schedule."),
    ("message", "#16a34a", "Ask about any move",
     "Share a game with the community, get answers from fellow players, and earn points for helping others."),
]
STUDY = [("Openings", "#2748c7"), ("Model games", "#0d9488"), ("Attack academy", "#e0533d"), ("Think like a Grandmaster", "#7c3aed")]


def svg_icon(name: str) -> str:
    return (f'<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round"><path d="{ICONS[name]}"/></svg>')


def flyer(n: int) -> str:
    feats = "".join(
        f'<div class="feat" style="--c:{c}"><div class="ic">{svg_icon(i)}</div><div><h3>{t}</h3><p>{d}</p></div></div>'
        for i, c, t, d in FEATURES)
    study = "".join(f'<span style="--c:{c}">{x}</span>' for x, c in STUDY)
    return f"""
<section class="flyer"><div class="panel">
  <header class="band">
    <div class="logo">{logo.replace("{n}", str(n))}</div>
    <div>
      <div class="name">Chess Varsity <span class="beta">BETA</span></div>
      <div class="tag">Free chess coach and planner</div>
    </div>
  </header>

  <h1>Your tournament games hold the key to your <mark>next rating jump.</mark></h1>
  <p class="lead">Most chess apps are made for playing online. Chess Varsity turns the games you battle through
    over the board into a coaching plan made just for you.</p>

  <div class="label"><span>What makes us different</span></div>
  <div class="feats">{feats}</div>

  <div class="study"><b>Level up with</b>{study}</div>

  <footer class="cta">
    <div class="qr">{qr}</div>
    <div class="cta-text">
      <div class="scan">Scan &amp; start free</div>
      <div class="url">ChessVarsity.com</div>
      <p>Phone, tablet or computer. Nothing to install.</p>
      <p class="soon"><span class="spark">★</span> AI coming soon: ask about any position and get deeper analysis like never before.</p>
    </div>
  </footer>
</div></section>"""


fonts = "../src/chesscoach/static/fonts"
html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Chess Varsity flyer</title>
<style>
@font-face {{ font-family: Figtree; src: url("{fonts}/figtree-400-normal.woff2") format("woff2"); font-weight: 400; }}
@font-face {{ font-family: Figtree; src: url("{fonts}/figtree-500-normal.woff2") format("woff2"); font-weight: 500; }}
@font-face {{ font-family: Figtree; src: url("{fonts}/figtree-600-normal.woff2") format("woff2"); font-weight: 600; }}
@font-face {{ font-family: Figtree; src: url("{fonts}/figtree-700-normal.woff2") format("woff2"); font-weight: 700; }}
:root {{ --navy: #0d1836; --royal: #2748c7; --gold: #d99a0b; --gold-2: #ffd166; --ink: #0e1a3a; --muted: #4a5478; }}
@page {{ size: A4 landscape; margin: 0; }}
* {{ box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
html, body {{ margin: 0; background: #fff; color: var(--ink); font-family: Figtree, "Segoe UI", Arial, sans-serif; }}
.sheet {{ width: 297mm; height: 210mm; display: grid; grid-template-columns: 1fr 1fr; position: relative; overflow: hidden; background: #fff; }}
.sheet::after {{ content: ""; position: absolute; left: 50%; top: 0; bottom: 0; border-left: 0.3mm dashed #b8bfd6; }}
.cut {{ position: absolute; left: 50%; top: 1.5mm; transform: translateX(-50%) rotate(90deg); font-size: 10pt; color: #9aa3c0; background: #fff; z-index: 1; line-height: 1; }}
.flyer {{ padding: 6mm; height: 210mm; }}
.panel {{ height: 100%; border-radius: 5mm; padding: 4mm; display: flex; flex-direction: column; gap: 2.5mm;
  background: radial-gradient(120% 60% at 100% 0%, #e7ecff 0%, rgba(231,236,255,0) 60%),
              radial-gradient(90% 50% at 0% 100%, #fff1cc 0%, rgba(255,241,204,0) 65%), #fbfbfe;
  border: 0.3mm solid #e3e7f5; }}
.panel > * {{ flex-shrink: 0; }}

.band {{ position: relative; overflow: hidden; color: #fff; border-radius: 4mm; padding: 3.8mm 4.5mm; display: flex; align-items: center; gap: 3.6mm;
  background: linear-gradient(120deg, #0d1836 0%, #182c78 60%, #2748c7 100%); border-bottom: 1.3mm solid var(--gold); }}
.band::after {{ content: ""; position: absolute; right: -4mm; top: -4mm; width: 34mm; height: 34mm; opacity: .13; transform: rotate(12deg);
  background: repeating-conic-gradient(#ffd166 0 25%, transparent 0 50%) 0 0 / 8mm 8mm; }}
.logo svg {{ width: 15mm; height: 15mm; display: block; filter: drop-shadow(0 0.6mm 1mm rgba(0,0,0,.35)); }}
.name {{ font-size: 19pt; font-weight: 700; letter-spacing: -0.2pt; line-height: 1.05; }}
.beta {{ font-size: 6.5pt; font-weight: 700; background: var(--gold-2); color: var(--navy); border-radius: 1mm; padding: 0.6mm 1.5mm; vertical-align: middle; letter-spacing: 0.6pt; position: relative; top: -1mm; }}
.tag {{ color: var(--gold-2); font-size: 9.6pt; font-weight: 600; margin-top: 0.8mm; }}

h1 {{ font-size: 15.5pt; line-height: 1.16; margin: 0.8mm 0 0; color: var(--navy); letter-spacing: -0.2pt; }}
h1 mark {{ background: #fff1c2; color: var(--royal); border-radius: 1.4mm; padding: 0.2mm 1.4mm 0.6mm; white-space: nowrap; box-decoration-break: clone; }}
.lead {{ font-size: 8.8pt; line-height: 1.4; margin: 0; color: var(--muted); }}
.label {{ display: flex; align-items: center; gap: 2mm; font-size: 7.8pt; font-weight: 700; letter-spacing: 1pt; text-transform: uppercase; color: #b07600; }}
.label::before, .label::after {{ content: ""; height: 0.3mm; flex: 1; background: linear-gradient(90deg, transparent, #e7b949); }}
.label::after {{ background: linear-gradient(90deg, #e7b949, transparent); }}

.feats {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2mm; }}
.feat {{ display: flex; gap: 2.2mm; border-radius: 2.6mm; padding: 2.3mm 2.4mm; background: #fff;
  background-image: linear-gradient(135deg, color-mix(in srgb, var(--c) 11%, #fff), #fff 70%);
  border: 0.3mm solid color-mix(in srgb, var(--c) 28%, #fff); border-top: 1mm solid var(--c); }}
.ic {{ flex: none; width: 7.6mm; height: 7.6mm; border-radius: 2.2mm; background: var(--c); display: grid; place-items: center;
  box-shadow: 0 0.6mm 1.4mm color-mix(in srgb, var(--c) 45%, transparent); }}
.ic svg {{ width: 4.6mm; height: 4.6mm; }}
.feat h3 {{ font-size: 8.9pt; line-height: 1.2; margin: 0 0 0.7mm; color: color-mix(in srgb, var(--c) 70%, #0d1836); }}
.feat p {{ font-size: 7.4pt; line-height: 1.32; margin: 0; color: var(--muted); }}

.study {{ display: flex; flex-wrap: wrap; align-items: center; gap: 1.3mm; font-size: 8pt; color: var(--navy); }}
.study b {{ margin-right: 0.8mm; }}
.study span {{ color: #fff; background: var(--c); border-radius: 99mm; padding: 0.8mm 2.4mm; font-weight: 600; font-size: 7.7pt; }}

.cta {{ margin-top: auto; display: flex; align-items: center; gap: 4.5mm; border-radius: 4mm; padding: 3.4mm 4mm;
  background: linear-gradient(120deg, #ffd166 0%, #f7b733 100%); box-shadow: inset 0 0 0 0.4mm rgba(13,24,54,.12); }}
.qr {{ flex: none; width: 31mm; height: 31mm; padding: 2mm; background: #fff; border-radius: 2.5mm; }}
.qr svg {{ width: 100%; height: 100%; display: block; }}
.scan {{ font-size: 17pt; font-weight: 700; color: var(--navy); line-height: 1.1; }}
.url {{ display: inline-block; font-size: 12.5pt; font-weight: 700; color: #fff; background: var(--navy); border-radius: 1.6mm; padding: 0.8mm 2.4mm; margin: 1.4mm 0 1.8mm; }}
.cta p {{ margin: 0; font-size: 8.2pt; line-height: 1.35; color: #3d3100; }}
.cta p.soon {{ margin-top: 1.2mm; color: var(--navy); font-weight: 700; }}
.spark {{ display: inline-grid; place-items: center; width: 4.2mm; height: 4.2mm; border-radius: 50%; background: var(--navy); color: var(--gold-2); font-size: 7pt; vertical-align: -0.8mm; margin-right: 0.6mm; }}
@media screen {{ body {{ background: #e5e8f2; padding: 10mm 0; }} .sheet {{ margin: 0 auto; box-shadow: 0 2mm 8mm rgba(13,24,54,.18); }} }}
</style>
</head>
<body>
<main class="sheet">
  <span class="cut" aria-hidden="true">✂</span>
  {flyer(1)}
  {flyer(2)}
</main>
</body>
</html>
"""
(HERE / "flyer.html").write_text(html, encoding="utf-8", newline="\n")

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1123, "height": 794}, device_scale_factor=2)
    pg.goto((HERE / "flyer.html").as_uri())
    pg.evaluate("document.fonts.ready")
    pg.wait_for_timeout(300)
    over = pg.evaluate("[...document.querySelectorAll('.panel')].map(f => f.scrollHeight - f.clientHeight)")
    print("overflow px per flyer:", over)
    pg.emulate_media(media="print")
    pg.screenshot(path=str(HERE / "flyer.png"))
    pg.pdf(path=str(HERE / "flyer.pdf"), format="A4", landscape=True, print_background=True,
           margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
    b.close()
print("wrote", HERE / "flyer.html", HERE / "flyer.pdf")
