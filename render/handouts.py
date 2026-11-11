"""Handouts page: whole_files rows with use=print."""
from render.common import simple_page, text
from render.sources import doc_card

HEAD = '<link rel="stylesheet" href="assets/content.css">'


def render(ctx):
    cards = [doc_card(ctx, w) for w in ctx["sel"].get("whole_files", []) if text(w, "use") == "print"]
    page = simple_page(ctx, "handouts", cards)
    page.head_extra = HEAD
    return page
