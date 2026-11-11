"""Posters page: A3 poster page images, hosted only when the source is licensed; otherwise 'Printed copy at the talk'."""
from pathlib import Path

from render.common import actions, card, esc, file_size_label, link, poster_facts, printed_note, simple_page, text
from render.sources import poster_image

HEAD = '<link rel="stylesheet" href="assets/content.css">'


def poster_card(ctx, p):
    title = text(p, "title")
    why_html = ""
    img = poster_image(ctx, p)
    source, date, lic = poster_facts(ctx, p)
    if not img:
        return card("poster", title, source, date, "A3 poster", printed_note())
    size = file_size_label(ctx["out"] / img["src"])
    fig = (f'<a class="card-figure-link" style="aspect-ratio: {img["thumb_width"]} / {img["thumb_height"]}" data-link="file" href="{esc(img["src"])}" '
           f'aria-label="Full-size image of {esc(title)}, PNG, {size}">'
           f'<img src="{esc(img["thumb"])}" width="{img["thumb_width"]}" height="{img["thumb_height"]}" '
           f'loading="lazy" alt="{esc(title)} (A3 poster)"></a>\n')
    facts = '<p class="card-note">A3 poster</p>\n'
    body = fig + facts + why_html + actions(link("file", img["src"], f"Full-size image (PNG, {size})", f"Full-size image (PNG, {size}): {title}")) + lic
    return card("poster", title, source, date, "A3 poster", body)


def render(ctx):
    cards = [poster_card(ctx, p) for p in ctx["sel"].get("posters_a3", [])]
    page = simple_page(ctx, "posters", cards)
    page.head_extra = HEAD
    return page
