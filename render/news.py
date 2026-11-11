"""News page: external-link cards with outlet, date and kind (news or commentary)."""
from render.common import (actions, card, fmt_date, link, host_of, printed_note, safe_external, simple_page, text)

HEAD = '<link rel="stylesheet" href="assets/content.css">'


def render(ctx):
    cards = []
    for n in ctx["sel"].get("news", []):
        url = safe_external(text(n, "url"))
        src = text(n, "outlet") or host_of(url) or "Printed copy"
        badge = "Commentary" if text(n, "kind").lower() == "commentary" else "News"
        body = actions(link("external", url, f"Opens {src}", f"Opens {src}: {text(n, 'title')}")) if url else printed_note()
        cards.append(card("news", text(n, "title"), src, fmt_date(n.get("date")), badge, body))
    page = simple_page(ctx, "news", cards)
    page.head_extra = HEAD
    return page
