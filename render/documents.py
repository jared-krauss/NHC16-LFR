"""Documents page: whole_files rows with use=host or use=link."""
from render.common import simple_page, text
from render.sources import doc_card

HEAD = '<link rel="stylesheet" href="assets/content.css">'


def render(ctx):
    cards = [doc_card(ctx, w) for w in ctx["sel"].get("whole_files", []) if text(w, "use") in ("host", "link")]
    page = simple_page(ctx, "documents", cards)
    page.head_extra = HEAD
    return page
