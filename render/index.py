"""Home page: talk facts, one card per section, and the share block with the QR code."""
from render import Page, load
from render.common import count_for, count_label, esc, label, link, EMPTY_TEXT


def _count(ctx, slug):
    mod = load(slug)
    fn = getattr(mod, "count", None)
    try:
        return int(fn(ctx)) if fn else count_for(ctx, slug)
    except Exception:
        return 0


def render(ctx):
    site = ctx["config"]["site"]
    cards = []
    for s in ctx["config"]["sections"]:
        if s["slug"] == "index":
            continue
        n = _count(ctx, s["slug"])
        noun = s.get("noun")
        note = (f"{n} {noun}" + ("" if n == 1 else "s") if noun else count_label(n)) if n else EMPTY_TEXT
        cards.append(
            '<article class="card" data-kind="section">\n'
            f'<h2 class="card-title">{link("page", s["slug"] + ".html", s["label"])}</h2>\n'
            f'<p class="card-count">{esc(note)}</p>\n</article>')
    facts = (f'<div class="talk-facts">\n<p>{esc(site.get("speaker"))}</p>\n<p>{esc(site.get("event"))}</p>\n'
             f'<p>{esc(site.get("date"))}</p>\n</div>')
    qr = ctx.get("qr") or {}
    share = ('<section class="share" aria-labelledby="share-h">\n<h2 id="share-h">Share this site</h2>\n'
             f'<img src="qr.svg" width="{qr.get("px", 200)}" height="{qr.get("px", 200)}" loading="lazy" '
             f'alt="QR code for {esc(site["public_url"])}">\n'
             f'<p class="share-url">{esc(site["public_url"])}</p>\n</section>')
    body = facts + '\n<div class="cards">\n' + "\n".join(cards) + "\n</div>\n" + share
    return Page("index", site["talk_title"], site["talk_title"], body)
