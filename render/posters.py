"""Posters page: A3 poster page images, hosted only when the source is licensed; otherwise 'Printed copy at the talk'."""
from pathlib import Path

from render.common import (actions, card, esc, file_size_label, fmt_date, host_of, item_path, link, printed_note,
                           safe_external, simple_page, text)
from render.sources import poster_image

HEAD = '<link rel="stylesheet" href="assets/content.css">'


def poster_card(ctx, p):
    title = text(p, "title")
    page_no = p.get("page") if isinstance(p.get("page"), int) else None
    page_txt = f"page {page_no}" if page_no else "page"
    why_html = ""
    img = poster_image(ctx, p)
    source = host_of(safe_external(text(p, "source_url"))) or "Printed copy"
    if not img:
        return card("poster", title, source, fmt_date(p.get("date")), "A3 poster",
                    why_html + (f'<p class="card-note">A3 poster, {page_txt}</p>\n' if page_no else "") + printed_note())
    size = file_size_label(ctx["out"] / img["src"])
    fig = (f'<a class="card-figure-link" style="aspect-ratio: {img["thumb_width"]} / {img["thumb_height"]}" data-link="file" href="{esc(img["src"])}" '
           f'aria-label="Full-size image of {esc(title)}, PNG, {size}">'
           f'<img src="{esc(img["thumb"])}" width="{img["thumb_width"]}" height="{img["thumb_height"]}" '
           f'loading="lazy" alt="{esc(title)} (A3 poster, {page_txt})"></a>\n')
    facts = f'<p class="card-note">A3 poster, {page_txt}</p>\n'
    body = fig + facts + why_html + actions(link("file", img["src"], f"Full-size image (PNG, {size})", f"Full-size image (PNG, {size}): {title}"))
    return card("poster", title, source, fmt_date(p.get("date")), "A3 poster", body)


def render(ctx):
    cards = [poster_card(ctx, p) for p in ctx["sel"].get("posters_a3", [])]
    page = simple_page(ctx, "posters", cards)
    page.head_extra = HEAD
    return page
