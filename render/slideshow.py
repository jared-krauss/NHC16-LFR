"""Slideshow page: one list of contract cards that works without JS; assets/slideshow.js turns it into a carousel."""
from render import Page
from render.common import (card, empty_state, esc, fmt_date, host_file, item_path, label, licence_for, norm_path,
                           photo_cleared, poster_facts, project_path, sel_items, slideshow_items, text)

try:
    from render import sources
except ImportError:
    sources = None

TEXT_HEAVY_CHARS = 160


def _call(name, ctx, arg):
    """Call a sources.py helper; None when the module, the helper or the image is missing."""
    fn = getattr(sources, name, None) if sources else None
    if not fn:
        return None
    try:
        return fn(ctx, arg)
    except Exception as e:
        print(f"slideshow: {name} failed for {arg!r}: {e}")
        return None


def _find(ctx, key, ref, page=None):
    """The selections row with this source path (and, when given, this page number)."""
    want = norm_path(ref)
    for it in sel_items(ctx, key):
        if norm_path(item_path(it)) == want and (page in (None, "") or it.get("page") == page):
            return it
    return None


def _image_size(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def _resolve(ctx, it):
    """Turn one slideshow entry into a slide dict, or None (with a printed reason) when it cannot be shown."""
    kind, ref = it["kind"], it["ref"]
    if kind == "chart":
        img = _call("chart_image", ctx, ref)
        if not img:
            print(f"slideshow: skipped chart {ref} (no image)")
            return None
        return dict(kind="chart", badge="Chart", title=img.get("title") or ref,
                    source=img.get("source_line") or "Chart", date="", caption="", img=img)
    if kind == "figure":
        from render.media import figures, source_line
        f = next((x for x in figures(ctx) if str(x["n"]) == str(ref)), None)
        if not f:
            print(f"slideshow: skipped Fig. {ref} (not found)")
            return None
        from render import bibliography
        date = bibliography.entry_date(ctx, f["source_id"]) if bibliography.has_entry(ctx, f["source_id"]) else ""
        img = {"src": f["web"], "thumb": f["thumb"], "width": f["web_w"], "height": f["web_h"], "alt": f["alt"]}
        return dict(kind="figure", badge="Illustration" if f["kind"] != "chart" else "Chart",
                    title=f"Fig. {f['n']}: {f['title']}", source=source_line(ctx, f), date=date, caption="", img=img)
    if kind == "poster":
        row = _find(ctx, "posters_a3", ref, it.get("page"))
        img = _call("poster_image", ctx, row) if row else None
        if not img:
            print(f"slideshow: skipped poster {ref} (no image)")
            return None
        src, date, lic = poster_facts(ctx, row)
        return dict(kind="poster", badge="Poster", title=img.get("title") or text(row, "title"), source=src,
                    date=date, caption="", img=img, licence=lic)
    if kind == "photo":
        row = _find(ctx, "photos", ref)
        if not row or not photo_cleared(ctx, ref):
            print(f"slideshow: skipped photo {ref} (not cleared)")
            return None
        rel = host_file(ctx, ref, "files")
        size = _image_size(project_path(ref)) if rel else None
        if not rel or not size:
            print(f"slideshow: skipped photo {ref} (file unusable)")
            return None
        return dict(kind="photo", badge="Photo", title=text(row, "title"), source=licence_for(ctx, ref) or "Photo",
                    date=fmt_date(row.get("date")), caption=text(row, "caption"),
                    img={"src": rel, "width": size[0], "height": size[1]})
    if kind == "video":
        row = _find(ctx, "splats", ref)
        rel = host_file(ctx, ref, "files") if row else None
        if not rel:
            print(f"slideshow: skipped video {ref}")
            return None
        return dict(kind="video", badge="Video", title=text(row, "title"), source="Video", date="",
                    caption="", img={"src": rel, "width": 1280, "height": 720})
    print(f"slideshow: skipped {kind} {ref} (kind not supported)")
    return None


def _dwell(slide, cfg):
    """Seconds on screen: 0 for video (advances on 'ended'), text_heavy for long text, else chart or image."""
    d = cfg.get("dwell_seconds") or {}
    if slide["kind"] == "video":
        return 0
    if len(slide["title"]) + len(slide["caption"]) + len(slide["source"]) > TEXT_HEAVY_CHARS:
        return d.get("text_heavy", 11)
    return d.get("chart" if slide["kind"] == "chart" else "image", 7)


def _srcset(ctx, img):
    """srcset (thumb + large, w descriptors) when a smaller candidate exists, else ''."""
    thumb, src = img.get("thumb"), img.get("src")
    if not thumb or thumb == src:
        return ""
    size = _image_size(ctx["out"] / thumb)
    w = int(img.get("width") or 0)
    if not size or not w or size[0] >= w:
        return ""
    return f' srcset="{esc(thumb)} {size[0]}w, {esc(src)} {w}w" sizes="(min-width: 60rem) 90vw, 100vw"'


def _body(ctx, slide, first):
    img = slide["img"]
    w, h = int(img.get("width") or 1200), int(img.get("height") or 800)
    alt = esc(img.get("alt") or slide["title"] or slide["badge"])
    if slide["kind"] == "video":
        media = (f'<video src="{esc(img["src"])}" muted playsinline preload="metadata" width="{w}" height="{h}" '
                 f'aria-label="{alt}"></video>')
    else:
        lazy = "" if first else ' loading="lazy"'
        media = f'<img src="{esc(img["src"])}"{_srcset(ctx, img)} width="{w}" height="{h}" alt="{alt}"{lazy}>'
    body = f'<div class="slide-media">{media}</div>\n'
    if slide["caption"]:
        body += f'<p class="slide-caption">{esc(slide["caption"])}</p>\n'
    body += slide.get("licence", "")
    return body


def render(ctx):
    lab = label(ctx, "slideshow")
    cfg = ctx["config"].get("slideshow") or {}
    slides = [s for s in (_resolve(ctx, i) for i in slideshow_items(ctx)) if s]
    head = '<link rel="stylesheet" href="assets/slideshow.css">'
    if not slides:
        return Page("slideshow", lab, lab, empty_state(lab), head_extra=head)
    head += '\n<script>document.documentElement.classList.add("slide-live")</script>'
    key, _, val = str(cfg.get("paused_param", "auto=0")).partition("=")
    lis = []
    for n, s in enumerate(slides):
        c = card(s["kind"] if s["kind"] in ("chart", "poster", "figure") else "link", s["title"], s["source"], s["date"],
                 s["badge"], _body(ctx, s, n == 0))
        c = c.replace('class="card-title"', 'class="card-title slide-title"', 1)
        lis.append(f'<li class="slide" data-dwell="{_dwell(s, cfg)}">{c}</li>')
    autoplay = "1" if cfg.get("autoplay_default", True) else "0"
    html = (f'<section id="slideshow" aria-roledescription="carousel" aria-label="{esc(lab)}" '
            f'data-pause-key="{esc(key)}" data-pause-val="{esc(val)}" data-autoplay="{autoplay}">\n'
            '<div class="slide-bar">\n'
            '<button type="button" data-action="pause">Pause</button>\n'
            '<button type="button" data-action="prev" aria-label="Previous slide">&larr; Prev</button>\n'
            f'<span class="slide-counter">1 / {len(slides)}</span>\n'
            '<button type="button" data-action="next" aria-label="Next slide">Next &rarr;</button>\n'
            '<button type="button" data-action="fullscreen">Full screen</button>\n'
            '<a class="slide-home" data-link="page" href="index.html">Home</a>\n'
            '<button type="button" data-action="exit">Exit</button>\n'
            '</div>\n<div class="slide-stage">\n<ul class="slide-list">\n' + "\n".join(lis) + '\n</ul>\n</div>\n</section>')
    return Page("slideshow", lab, lab, html, head_extra=head,
                scripts_extra='<script src="assets/slideshow.js" defer></script>')
