"""Media page: numbered figures (illustrations and charts), each opening in a zoomable viewer.

Figure numbers, titles, alt text and source facts come only from figures-config.json. Images are copied to
media/ (web = 1600 px webp for the page and slideshow, thumb = 640 px webp, full = the original PNG for the viewer).
Charts from charts_ready that are not in the figures file appear unnumbered after the figures; charts still being
tweaked are summarised as one note.
"""
import json
from pathlib import Path

from render import Page
from render.common import (actions, card, empty_card, empty_state, esc, file_size_label, host_of, label, link,
                           safe_external, text)
from render.sources import chart_record, chart_title

HEAD = ('<link rel="stylesheet" href="assets/content.css">\n<link rel="stylesheet" href="assets/media.css">\n'
        '<link rel="stylesheet" href="assets/viewer.css">')
SCRIPTS = '<script src="assets/viewer.js" defer></script>\n<script src="assets/media.js" defer></script>'


def size_mb(n):
    """Approximate download size, e.g. '5.1 MB'."""
    return f"{n / (1024 * 1024):.1f} MB"


def _dims(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


TRIM_LIMIT = 0.04
TRIM_PAD = 0.015


def _trim_box(path):
    """Fractional crop box (l, t, r, b) that trims a figure's uneven white margin, or None when the margins are even enough."""
    try:
        import os
        import stat
        from PIL import Image, ImageChops
        os.chmod(path, stat.S_IWRITE)
        with Image.open(path) as im:
            rgb = im.convert("RGB")
            bb = ImageChops.difference(rgb, Image.new("RGB", rgb.size, (255, 255, 255))).point(lambda v: 255 if v > 12 else 0).getbbox()
            w, h = rgb.size
        if not bb:
            return None
        l, t, r, b = bb[0] / w, bb[1] / h, (w - bb[2]) / w, (h - bb[3]) / h
        if max(l, t, r, b) <= TRIM_LIMIT:
            return None
        pad = TRIM_PAD * max(w, h)
        return (max(0, bb[0] - pad) / w, max(0, bb[1] - pad) / h, min(w, bb[2] + pad) / w, min(h, bb[3] + pad) / h)
    except Exception:
        return None


def _apply_trim(path, box):
    """Crop a copied site image to a fractional box (never the original file)."""
    try:
        import os
        import stat
        from PIL import Image
        os.chmod(path, stat.S_IWRITE)
        with Image.open(path) as im:
            im.load()
            w, h = im.size
            cropped = im.crop((round(box[0] * w), round(box[1] * h), round(box[2] * w), round(box[3] * h)))
            fmt = im.format
        if fmt == "WEBP":
            cropped.save(path, "WEBP", quality=90, method=6)
        else:
            cropped.save(path, fmt)
    except Exception:
        pass


def figures(ctx):
    """The figures from figures-config.json with their images copied into the site, sorted by number."""
    if "_figures" in ctx:
        return ctx["_figures"]
    ctx["_figures"] = []
    name = ctx["config"].get("figures_config")
    p = ctx["root"] / name if name else None
    if not p or not p.is_file():
        ctx["log"]("media: no figures-config.json; Media shows 'On its way'")
        return ctx["_figures"]
    try:
        rows = json.loads(p.read_text(encoding="utf-8-sig")).get("figures", [])
    except (OSError, ValueError) as e:
        ctx["log"](f"media: figures-config.json unreadable ({type(e).__name__})")
        return ctx["_figures"]
    out = []
    for r in rows:
        if not isinstance(r, dict) or not isinstance(r.get("n"), int) or not text(r, "title"):
            ctx["log"]("media: figure without a number or title skipped")
            continue
        n = r["n"]
        src = {k: text(r, k) for k in ("image", "web", "thumb")}
        web = src["web"] or src["image"]
        full = src["image"] or web
        if not web or not Path(web).is_file():
            ctx["log"](f"media: Fig. {n} has no web image; skipped")
            continue
        web_rel = ctx["copy_asset"](web, f"media/fig-{n}.webp" if web.lower().endswith(".webp") else f"media/fig-{n}{Path(web).suffix.lower()}")
        thumb_rel = None
        if src["thumb"] and Path(src["thumb"]).is_file():
            thumb_rel = ctx["copy_asset"](src["thumb"], f"media/fig-{n}-thumb{Path(src['thumb']).suffix.lower()}")
        full_rel = web_rel
        if full and Path(full).is_file() and full != web:
            full_rel = ctx["copy_asset"](full, f"media/fig-{n}-full{Path(full).suffix.lower()}") or web_rel
        if not web_rel:
            continue
        box = _trim_box(ctx["out"] / full_rel)
        if box:
            for rel in {web_rel, thumb_rel, full_rel} - {None}:
                _apply_trim(ctx["out"] / rel, box)
            ctx["log"](f"media: Fig. {n} white margin trimmed on the site copies")
        wd = _dims(ctx["out"] / web_rel) or (1600, 1000)
        td = _dims(ctx["out"] / thumb_rel) if thumb_rel else None
        out.append({"n": n, "id": text(r, "id"), "title": text(r, "title"), "kind": text(r, "kind") or "illustration",
                    "alt": text(r, "alt") or text(r, "title"), "source_id": text(r, "source_id"),
                    "source_title": text(r, "source_title"), "printed_page": text(r, "printed_page"), "pdf_page": r.get("pdf_page") if isinstance(r.get("pdf_page"), int) else None,
                    "source_url": safe_external(text(r, "source_url")), "web": web_rel, "web_w": wd[0], "web_h": wd[1],
                    "thumb": thumb_rel or web_rel, "thumb_w": td[0] if td else wd[0], "thumb_h": td[1] if td else wd[1],
                    "full": full_rel, "full_ext": Path(full_rel).suffix.lstrip(".").upper(),
                    "full_size": file_size_label(ctx["out"] / full_rel)})
    out.sort(key=lambda f: f["n"])
    ctx["_figures"] = out
    return out


def source_line(ctx, f):
    """Plain text 'title, p. N' for a figure's source, using the Bibliography's one title for that document."""
    from render import bibliography
    title = bibliography.entry_title(ctx, f["source_id"], f["source_title"])
    return f"{title}, p. {f['printed_page']}" if f["printed_page"] else title


def count(ctx):
    return len(figures(ctx))


def _figure_card(ctx, f):
    from render import bibliography
    title = bibliography.entry_title(ctx, f["source_id"], f["source_title"])
    date = bibliography.entry_date(ctx, f["source_id"]) if bibliography.has_entry(ctx, f["source_id"]) else ""
    if bibliography.has_entry(ctx, f["source_id"]):
        src_name = link("page", f"bibliography.html#{f['source_id']}", title)
    else:
        src_name = esc(title)
    if f["printed_page"]:
        hosted = bibliography.entry_hosted(ctx, f["source_id"])
        if hosted and f["pdf_page"]:
            size = file_size_label(ctx["out"] / hosted)
            src_name += (f', <a data-link="file" href="{esc(hosted)}#page={f["pdf_page"]}" target="_blank" rel="noopener" '
                         f'aria-label="{esc("Open page " + f["printed_page"] + " of the PDF (PDF, " + size + ")")}">p. {esc(f["printed_page"])}</a>')
        else:
            src_name += f", p. {esc(f['printed_page'])}"
    badge = "Chart" if f["kind"] == "chart" else "Illustration"
    srcset = f'{esc(f["thumb"])} {f["thumb_w"]}w, {esc(f["web"])} {f["web_w"]}w' if f["thumb"] != f["web"] else ""
    srcattr = f' srcset="{srcset}" sizes="(min-width: 60rem) 30vw, (min-width: 40rem) 45vw, 100vw"' if srcset else ""
    aria = f"Open Fig. {f['n']} full size: {f['title']} ({f['full_ext']}, {f['full_size']})"
    img = (f'<a class="fig-image" data-link="file" href="{esc(f["full"])}" data-web="{esc(f["web"])}" '
           f'data-w="{f["web_w"]}" data-h="{f["web_h"]}" aria-label="{esc(aria)}">'
           f'<img src="{esc(f["thumb"])}"{srcattr} width="{f["thumb_w"]}" height="{f["thumb_h"]}" loading="lazy" '
           f'alt="{esc(f["alt"])}"></a>\n')
    date_span = f'<span class="date">{esc(date)}</span>' if date else ""
    links = []
    if f["kind"] == "chart":
        rec = chart_record(ctx, f["id"])
        if rec:
            lab = f'Open interactive chart (about {size_mb(rec["weight"])} download)'
            links.append(link("page", rec["page"], lab, f'{lab}: {f["title"]}'))
    if f["source_url"]:
        host = host_of(f["source_url"])
        links.append(link("external", f["source_url"], f"Opens {host} (PDF)", f"Opens {host} (PDF): {title}"))
    return (f'<article class="card fig-card" id="fig-{f["n"]}" data-kind="figure">\n'
            f'<h2 class="card-title"><span class="fig-label">Fig. {f["n"]}</span> '
            f'<span class="fig-title">{esc(f["title"])}</span></h2>\n'
            f'<p class="card-meta">{date_span}<span class="card-kind">{badge}</span></p>\n'
            + img + f'<p class="fig-source card-meta">Source: {src_name}</p>\n' + actions(*links) + '</article>')


def _chart_card(rec):
    srcset = f'{esc(rec["thumb"])} {rec["thumb_width"]}w'
    if rec["large"] != rec["thumb"]:
        srcset += f', {esc(rec["large"])} {rec["width"]}w'
    fig = (f'<figure class="card-figure" style="aspect-ratio: {rec["thumb_width"]} / {rec["thumb_height"]}"><img '
           f'src="{esc(rec["thumb"])}" srcset="{srcset}" sizes="(min-width: 60rem) 30vw, (min-width: 40rem) 45vw, 100vw" '
           f'width="{rec["thumb_width"]}" height="{rec["thumb_height"]}" loading="lazy" '
           f'alt="{esc(rec["title"])} (static image of the chart)"></figure>\n')
    src = f'<p class="chart-source-line">{esc(rec["source_line"])}</p>\n' if rec["source_line"] else ""
    lab = f'Open interactive chart (about {size_mb(rec["weight"])} download)'
    body = fig + src + actions(link("page", rec["page"], lab, f'{lab}: {rec["title"]}'))
    return card("chart", rec["title"], "ALHFRS", rec.get("date", ""), "Chart", body)


def render(ctx):
    lab = label(ctx, "media")
    figs = figures(ctx)
    numbered = {f["id"] for f in figs if f["kind"] == "chart"}
    extra = []
    for c in ctx["sel"].get("charts_ready", []):
        cid = text(c, "id")
        if cid in numbered:
            continue
        rec = chart_record(ctx, cid)
        extra.append(_chart_card(rec) if rec else empty_card(chart_title(ctx, cid) or cid))
    pending = bool(ctx["sel"].get("charts_tweak"))
    if not figs and not extra and not pending:
        return Page("media", lab, lab, empty_state(lab), head_extra=HEAD)
    parts = []
    if len(figs) > 1:
        jump = "".join(f'<li>{link("anchor", "#fig-" + str(f["n"]), "Fig. " + str(f["n"]))}</li>' for f in figs)
        parts.append(f'<ul class="fig-jump" aria-label="Jump to a figure">{jump}</ul>')
    if figs:
        parts.append('<div class="fig-grid">\n' + "\n".join(_figure_card(ctx, f) for f in figs) + "\n</div>")
    if extra:
        parts.append('<div class="cards">\n' + "\n".join(extra) + "\n</div>")
    if pending:
        note = (ctx["config"].get("bibliography") or {}).get("chart_note", "More charts on their way")
        parts.append(f'<p class="media-note">{esc(note)}</p>')
    egg = ctx["config"].get("paper_menu_egg")
    if egg and egg.get("label"):
        parts.append('<script type="application/json" id="viewer-egg">' + json.dumps(egg, ensure_ascii=False).replace("</", "<\\/") + "</script>")
    return Page("media", lab, lab, "\n".join(parts), head_extra=HEAD, scripts_extra=SCRIPTS)
