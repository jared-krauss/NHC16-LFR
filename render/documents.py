"""Documents page: whole_files rows, grouped by their `group` field."""
from render.common import rows_page
from render.sources import doc_card

HEAD = '<link rel="stylesheet" href="assets/content.css">'


def render(ctx):
    page = rows_page(ctx, "documents", lambda w, level: doc_card(ctx, w, level))
    page.head_extra = HEAD
    return page
