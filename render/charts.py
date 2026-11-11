"""Charts page: a static image per ready chart linking to an on-site interactive page; tweak-pending charts as 'On its way'.

The listing page loads no chart library: each card shows a pre-rendered image only.
"""
from render.common import actions, card, empty_card, esc, link, simple_page, text
from render.sources import chart_record, chart_title

HEAD = '<link rel="stylesheet" href="assets/content.css">'


def size_mb(n):
    """Approximate download size, e.g. '5.1 MB'."""
    return f"{n / (1024 * 1024):.1f} MB"


def chart_card(rec):
    srcset = f'{esc(rec["thumb"])} {rec["thumb_width"]}w'
    if rec["large"] != rec["thumb"]:
        srcset += f', {esc(rec["large"])} {rec["width"]}w'
    fig = (f'<figure class="card-figure" style="aspect-ratio: {rec["thumb_width"]} / {rec["thumb_height"]}"><img src="{esc(rec["thumb"])}" srcset="{srcset}" '
           f'sizes="(min-width: 60rem) 30vw, (min-width: 40rem) 45vw, 100vw" '
           f'width="{rec["thumb_width"]}" height="{rec["thumb_height"]}" loading="lazy" '
                      f'alt="{esc(rec["title"])} (static image of the chart)"></figure>\n')
    src = f'<p class="chart-source-line">{esc(rec["source_line"])}</p>\n' if rec["source_line"] else ""
    label = f'Open interactive chart (about {size_mb(rec["weight"])} download)'
    body = fig + src + actions(link("page", rec["page"], label, f'{label}: {rec["title"]}'))
    return card("chart", rec["title"], "ALHFRS", rec.get("date", "Undated"), "Chart", body)


def render(ctx):
    cards = []
    for c in ctx["sel"].get("charts_ready", []):
        cid = text(c, "id")
        rec = chart_record(ctx, cid)
        if rec:
            cards.append(chart_card(rec))
        else:
            cards.append(empty_card(chart_title(ctx, cid) or cid))
    for c in ctx["sel"].get("charts_tweak", []):
        cid = text(c, "id")
        cards.append(empty_card(chart_title(ctx, cid) or cid))
    page = simple_page(ctx, "charts", cards)
    page.head_extra = HEAD
    return page
