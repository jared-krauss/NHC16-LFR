"""Shared asset resolvers for charts and posters (also imported by the slideshow builder).

chart_image(ctx, chart_id)  -> {"src","thumb","width","height","title","source_line"} or None
poster_image(ctx, poster_item) -> {"src","thumb","width","height","title"} or None

All returned urls are relative to the site root (docs/). Everything is built lazily and memoised in ctx, so any
page module may call these in any order. Nothing here writes prose: titles and source lines come from the chart file.
"""
import hashlib
import html as htmlmod
import json
import re
import shutil
import sys
from pathlib import Path

from render.common import esc, fmt_date, item_path, licence_for, norm_path, project_path, text

CACHE = Path(__file__).resolve().parent.parent / ".cache" / "nhc16"
PLOTLY_URL = "vendor/plotly/plotly-2.35.2.min.js"
D3_URL = "vendor/d3/d3-7.9.0.min.js"
LIB_FILES = {"plotly": PLOTLY_URL, "d3": D3_URL}
RENDER_VERSION = "3"
LARGE_WIDTH = 1600
BLOCKED_ALWAYS_WORDS = ["subject_name", "claimant", "respondent", "actor", "retrospective-fr", "enforcement-actions",
                        "arrest_", "custody_"]
DEFAULT_EXPORT_CFG = {
    "also_refuse": {},
    "blocked_data_files": ["retrospective-fr.json", "enforcement-actions.json"],
    "blocked_words": BLOCKED_ALWAYS_WORDS,
    "libs": {"d3.v7.min.js": "d3", "d3@7": "d3", "plotly-2.35.2.min.js": "plotly", "plotly-latest.min.js": "plotly"},
}
LIB_KEY = {"d3.v7.min.js": "d3", "d3@7": "d3", "d3@7.9.0": "d3", "plotly-2.35.2.min.js": "plotly", "plotly-latest.min.js": "plotly"}


def _log(ctx, msg):
    (ctx.get("log") or print)(msg)


def _gallery(ctx):
    return Path(ctx["config"].get("chart_gallery_dir") or "")


def _export_cfg(ctx):
    """Settings from the gallery exporter's own config (names rules), else safe defaults."""
    g = _gallery(ctx)
    cfg = dict(DEFAULT_EXPORT_CFG)
    p = g.parent / "gallery-export.json"
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for k in ("also_refuse", "blocked_data_files", "blocked_words"):
                if k in data:
                    cfg[k] = data[k]
        except (OSError, ValueError):
            pass
    return cfg


def _data(ctx):
    """(data, layers) parsed once from the gallery's alhfrs-data.js."""
    if "_chart_data" not in ctx:
        try:
            raw = (_gallery(ctx) / "alhfrs-data.js").read_text(encoding="utf-8")
            dec = json.JSONDecoder()
            data, _ = dec.raw_decode(raw[raw.index("{"):])
            j = raw.index("{", raw.index("ALHFRS_LAYERS"))
            layers, _ = dec.raw_decode(raw[j:])
            ctx["_chart_data"] = (data, layers)
        except (OSError, ValueError):
            ctx["_chart_data"] = ({}, {})
    return ctx["_chart_data"]


def _word_re(word):
    tail = "" if word.endswith("_") else r"(?![A-Za-z0-9_])"
    return re.compile(r"(?<![A-Za-z0-9_])" + re.escape(word) + tail)


def _find_chart_file(ctx, cid):
    g = _gallery(ctx)
    if not re.fullmatch(r"dv-\d{3}", cid or "") or not g.is_dir():
        return None
    for f in sorted(g.glob(cid + "*.html")):
        return f
    return None


def _title_of(src, cid):
    m = re.search(r"<title>(.*?)</title>", src, re.S | re.I)
    t = htmlmod.unescape(m.group(1)).strip() if m else ""
    return t or cid


def _source_line(src, keys):
    """The chart's own 'Source: ...' sentence, else a plain list of the data files it reads."""
    m = re.search(r"(Sources?:[^<>]{5,400})", src)
    if m:
        return re.sub(r"\s+", " ", htmlmod.unescape(m.group(1))).strip()
    names = ", ".join(k[:-5] if k.endswith(".json") else k for k in keys)
    return "Data: ALHFRS " + names if names else ""


def _build_page(ctx, cid, path):
    """Return (page_html, info) for one chart, or (None, reason). The page is self-contained apart from vendor/ and the kit."""
    src = path.read_text(encoding="utf-8")
    cfg = _export_cfg(ctx)
    if cid in cfg.get("also_refuse", {}):
        return None, cfg["also_refuse"][cid]
    for w in cfg["blocked_words"]:
        if _word_re(w).search(src):
            return None, "touches names or case details (" + w + ")"
    data, layers = _data(ctx)
    if not data:
        return None, "shared data file unreadable"
    blocked = set(cfg["blocked_data_files"])
    keys = sorted(set(re.findall(r"[\"']([\w-]+\.json)[\"']", src)) & set(data))
    if set(keys) & blocked:
        return None, "uses a data file that names people"
    dynamic = (not keys) or any(p in src for p in ("Object.keys(window.ALHFRS_DATA", "Object.entries(window.ALHFRS_DATA",
                                                    "Object.values(window.ALHFRS_DATA")) \
        or bool(re.search(r"ALHFRS_DATA\[\s*(?![\"'])", src))
    words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", src))
    proj = {}
    if dynamic:
        keys = [k for k in data if k not in blocked]
        bad_field = [_word_re(w) for w in cfg["blocked_words"]]
        for k in keys:
            proj[k] = [{f: v for f, v in r.items() if not any(b.fullmatch(f) or b.match(f) for b in bad_field)} for r in data[k]]
    else:
        for k in keys:
            used = [f for f in sorted({f for r in data[k] for f in r}) if f in words or f == "id"]
            proj[k] = [{f: r[f] for f in used if f in r} for r in data[k]]
    lkeys = sorted(set(re.findall(r"[\"']([\w-]+\.geojson)[\"']", src)) & set(layers))
    inline = "window.ALHFRS_DATA=" + json.dumps(proj, separators=(",", ":")) + ";"
    if lkeys:
        inline += "window.ALHFRS_LAYERS=" + json.dumps({k: layers[k] for k in lkeys}, separators=(",", ":")) + ";"
    page, n = re.subn(r'<script src="alhfrs-data\.js"[^>]*></script>', lambda m: "<script>" + inline.replace("</", "<\\/") + "</script>", src, count=1)
    if not n:
        return None, "does not load the shared data file in the expected way"
    libs = []

    def lib(m):
        for frag, key in LIB_KEY.items():
            if frag in m.group(1):
                libs.append(key)
                tag = '<script src="../%s"></script>' % LIB_FILES[key]
                if key == "plotly":
                    tag += '\n<script src="../assets/content.js"></script>'
                return tag
        return m.group(0)

    page = re.sub(r'<script src="(https://[^"]+)"[^>]*></script>', lib, page)
    if re.search(r'<(?:script|link)[^>]+(?:src|href)="https?://', page, re.I) or re.search(r"@import\s+url\(\s*['\"]?https?:", page, re.I):
        return None, "still loads something from the internet"
    left = re.findall(r'<(?:script|link)[^>]+(?:src|href)="(?!\.\./|data:|#|alhfrs-chartkit\.js)[^"]+"', page)
    if left:
        return None, "still needs local files"
    if not libs:
        return None, "uses no known chart library"
    source_line = _source_line(src, keys)
    title = _title_of(src, cid)
    page = re.sub(r"</head>", '<link rel="stylesheet" href="../assets/content.css">\n</head>', page, count=1, flags=re.I)
    page = re.sub(r"((?:min-)?height:\s*)100vh;", lambda m: m.group(0) + "\n      " + m.group(1) + "100dvh;", page)
    if re.search(r"<body[^>]*>", page, re.I):
        def body_open(m):
            tag = m.group(0)
            tag = re.sub(r'class="([^"]*)"', r'class="chart-page \1"', tag) if 'class="' in tag else tag[:-1] + ' class="chart-page">'
            return tag + "\n" + _frame_top(ctx) + '<main id="main">\n'
        page = re.sub(r"<body[^>]*>", body_open, page, count=1, flags=re.I)
    cls = re.search(r'<(\w+)([^>]*)>\s*Sources?:[^<]*</\1>', page)
    if cls and source_line.startswith("Source"):
        tag = cls.group(0)
        opening = "<%s%s>" % (cls.group(1), cls.group(2))
        newopen = (opening.replace('class="', 'class="chart-source ', 1) if 'class="' in opening
                   else "<%s class=\"chart-source\"%s>" % (cls.group(1), cls.group(2)))
        page = page.replace(tag, tag.replace(opening, newopen, 1), 1)
    else:
        extra = '<p class="chart-source">%s</p>\n' % esc(source_line or "Source: ALHFRS")
        page = re.sub(r"</body>", extra + "</body>", page, count=1, flags=re.I)
    page = re.sub(r"</body>", lambda m: "</main>\n" + _frame_bottom(ctx) + "</body>", page, count=1, flags=re.I)
    dm = re.search(r'<meta[^>]+name="(?:date|dcterms\.date)"[^>]+content="([^"]+)"', src, re.I)
    return page, {"title": title, "source_line": source_line, "libs": libs, "date": fmt_date(dm.group(1)) if dm else "Undated"}


def _frame_top(ctx):
    """Skip link and site header (nav from config, links one level up) for a chart page."""
    items = "\n".join('<li><a href="../%s.html">%s</a></li>' % (esc(x["slug"]), esc(x["label"]))
                      for x in ctx["config"].get("sections", []))
    name = ""
    seg = [q for q in ctx["config"]["site"].get("public_url", "").split("/") if q]
    name = seg[-1] if len(seg) > 1 else "Home"
    return ('<a class="skip-link" href="#main">Skip to content</a>\n<header class="cp-header">\n'
            '<a class="cp-name" href="../index.html">%s</a>\n<nav aria-label="Sections"><ul class="cp-nav">\n%s\n</ul></nav>\n</header>\n'
            % (esc(name), items))


def _frame_bottom(ctx):
    egg = "3D scenes"
    for h in ctx["config"].get("hidden_pages", []):
        if h.get("slug") == "scenes":
            egg = h.get("label", egg)
    return ('<footer class="cp-footer"><a class="egg" href="../scenes.html" aria-label="%s">'
            '<svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" focusable="false">'
            '<circle cx="6" cy="6" r="4.5" fill="none" stroke="currentColor" stroke-width="1.5"/></svg></a></footer>\n' % esc(egg))


def _choose_selector(pg):
    for sel in ("#chart-wrapper", ".js-plotly-plot", "#chart-container", "#chart", ".alhfrs-box", ".container", "body"):
        try:
            if pg.query_selector(sel):
                return sel
        except Exception:
            continue
    return "body"


def _render_png(page_file, dest):
    """Screenshot the chart element of a built page at about LARGE_WIDTH px wide. Returns True on success."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        try:
            pg = b.new_page(viewport={"width": 1280, "height": 1000})
            pg.goto(Path(page_file).resolve().as_uri(), wait_until="load")
            try:
                pg.wait_for_selector(".js-plotly-plot, svg, canvas", timeout=10000)
            except Exception:
                pass
            pg.wait_for_timeout(1500)
            sel = _choose_selector(pg)
            box = pg.eval_on_selector(sel, "e => { const r = e.getBoundingClientRect(); return [r.width, r.height]; }")
            scale = min(3.0, max(1.0, LARGE_WIDTH / max(box[0], 1)))
            pg.close()
            ctx2 = b.new_context(viewport={"width": 1280, "height": 1000}, device_scale_factor=scale)
            pg = ctx2.new_page()
            pg.goto(Path(page_file).resolve().as_uri(), wait_until="load")
            try:
                pg.wait_for_selector(".js-plotly-plot, svg, canvas", timeout=10000)
            except Exception:
                pass
            pg.wait_for_timeout(1500)
            pg.locator(sel).first.screenshot(path=str(dest))
        finally:
            b.close()
    return Path(dest).is_file()


def _image_size(path):
    from PIL import Image
    with Image.open(path) as im:
        return im.size


def chart_record(ctx, cid):
    """Build (once) the interactive page, thumb and large PNG for a chart; returns a record dict or None."""
    cache = ctx.setdefault("_chart_records", {})
    if cid in cache:
        return cache[cid]
    cache[cid] = None
    path = _find_chart_file(ctx, cid)
    if not path:
        _log(ctx, f"chart {cid}: not found in the gallery")
        return None
    page, info = _build_page(ctx, cid, path)
    if page is None:
        _log(ctx, f"chart {cid}: not published ({info})")
        return None
    out = ctx["out"]
    (out / "charts" / "img").mkdir(parents=True, exist_ok=True)
    (out / "charts" / f"{cid}.html").write_text(page, encoding="utf-8", newline="\n")
    kit = _gallery(ctx) / "alhfrs-chartkit.js"
    if kit.is_file():
        shutil.copy2(kit, out / "charts" / "alhfrs-chartkit.js")
    thumb_src = _gallery(ctx) / "thumbs" / f"{cid}.jpg"
    thumb = None
    if thumb_src.is_file():
        thumb = f"charts/img/{cid}-thumb.jpg"
        shutil.copy2(thumb_src, out / thumb)
    key = hashlib.sha1((RENDER_VERSION + page).encode("utf-8")).hexdigest()[:12]
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{cid}-{key}.png"
    if not cached.is_file():
        for old in CACHE.glob(f"{cid}-*.png"):
            old.unlink()
        try:
            _render_png(out / "charts" / f"{cid}.html", cached)
        except Exception as e:
            _log(ctx, f"chart {cid}: large image not rendered ({type(e).__name__})")
    large = None
    if cached.is_file():
        large = f"charts/img/{cid}-large.png"
        shutil.copy2(cached, out / large)
    if not thumb and not large:
        _log(ctx, f"chart {cid}: no image available")
        return None
    tw, th = _image_size(out / thumb) if thumb else _image_size(out / large)
    lw, lh = _image_size(out / large) if large else (tw, th)
    weight = (out / "charts" / f"{cid}.html").stat().st_size
    kit_out = out / "charts" / "alhfrs-chartkit.js"
    if kit_out.is_file():
        weight += kit_out.stat().st_size
    for lb in info["libs"]:
        f = ctx["root"] / LIB_FILES[lb]
        weight += f.stat().st_size if f.is_file() else 0
    rec = {"id": cid, "title": info["title"], "source_line": info["source_line"], "page": f"charts/{cid}.html",
           "thumb": thumb or large, "thumb_width": tw if thumb else lw, "thumb_height": th if thumb else lh,
           "large": large or thumb, "width": lw, "height": lh, "weight": weight, "date": info.get("date", "Undated")}
    cache[cid] = rec
    return rec


def chart_title(ctx, cid):
    """A chart's title from its own file, whether or not it can be published; '' when the file is missing."""
    p = _find_chart_file(ctx, cid)
    if not p:
        return ""
    try:
        return _title_of(p.read_text(encoding="utf-8"), cid)
    except OSError:
        return ""


def chart_image(ctx, chart_id):
    """Static images for a chart: src = large PNG (~1600 px), thumb = small JPEG. None when it cannot be published."""
    rec = chart_record(ctx, chart_id)
    if not rec:
        return None
    return {"src": rec["large"], "thumb": rec["thumb"], "width": rec["width"], "height": rec["height"],
            "title": rec["title"], "source_line": rec["source_line"]}


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "poster"


def _digest(ctx, p):
    cache = ctx.setdefault("_digests", {})
    k = norm_path(p)
    if k not in cache:
        pp = project_path(p)
        cache[k] = hashlib.sha1(pp.read_bytes()).hexdigest() if pp.is_file() else None
    return cache[k]


def _same_file(ctx, a, b):
    """Same path, or two different paths holding identical bytes (the same PDF filed twice)."""
    if norm_path(a) == norm_path(b):
        return True
    da = _digest(ctx, a)
    return bool(da) and da == _digest(ctx, b)


def _poster_png(ctx, item):
    """Find or make the page image on disk for a poster item: candidates.json PNG, else a full-page raster inside the PDF."""
    key = norm_path(item_path(item))
    page = item.get("page") if isinstance(item.get("page"), int) else 0
    d = Path(ctx["config"].get("poster_png_dir") or "")
    cj = d / "candidates.json"
    if cj.is_file():
        try:
            data = json.loads(cj.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            data = {}
        rows = [(c.get("source_file"), c.get("pdf_page"), None, c.get("png")) for c in data.get("candidates", [])]
        npl = data.get("npl_picks") or {}
        rows += [(npl.get("source"), pg.get("pdf_page"), pg.get("printed"), pg.get("png")) for pg in npl.get("pages", [])]
        for sf, pp, pr, png in rows:
            if sf and png and page in (pp, pr) and Path(png).is_file() and _same_file(ctx, sf, item_path(item)):
                return Path(png)
    src = project_path(item_path(item))
    if src.suffix.lower() == ".pdf" and src.is_file():
        try:
            from pypdf import PdfReader
            r = PdfReader(str(src))
            idx = max(page, 1) - 1
            pg = r.pages[idx]
            imgs = list(pg.images)
            w, h = float(pg.mediabox.width), float(pg.mediabox.height)
            if len(imgs) == 1:
                im = imgs[0].image
                if abs(im.width / im.height - w / h) / (w / h) < 0.05:
                    CACHE.mkdir(parents=True, exist_ok=True)
                    dest = CACHE / f"poster-{hashlib.sha1((key + str(page)).encode()).hexdigest()[:10]}.png"
                    im.convert("RGB").save(dest, "PNG")
                    return dest
        except Exception:
            return None
    return None


def poster_image(ctx, poster_item):
    """Hosted page image for a poster: {"src","thumb","width","height","title", ...} or None when unlicensed or not found."""
    if not isinstance(poster_item, dict):
        return None
    title = text(poster_item, "title")
    path = item_path(poster_item)
    cache = ctx.setdefault("_poster_records", {})
    ck = norm_path(path) + "|" + str(poster_item.get("page"))
    if ck in cache:
        return cache[ck]
    cache[ck] = None
    if not licence_for(ctx, path, text(poster_item, "licence_note")):
        return None
    png = _poster_png(ctx, poster_item)
    if not png:
        _log(ctx, f"poster '{title}': no page image found")
        return None
    from PIL import Image
    out = ctx["out"]
    (out / "posters").mkdir(parents=True, exist_ok=True)
    base = _slug(title) + "-" + hashlib.sha1(ck.encode()).hexdigest()[:6]
    full = f"posters/{base}.png"
    shutil.copy2(png, out / full)
    with Image.open(out / full) as im:
        w, h = im.size
        t = im.convert("RGB")
        t.thumbnail((640, 640))
        tw, th = t.size
        thumb = f"posters/{base}-thumb.jpg"
        t.save(out / thumb, "JPEG", quality=80, optimize=True)
    rec = {"src": full, "thumb": thumb, "width": w, "height": h, "title": title, "thumb_width": tw, "thumb_height": th,
           "bytes": (out / full).stat().st_size}
    cache[ck] = rec
    return rec


def doc_card(ctx, item, level=2):
    """Card for a whole_files row. Hosted file only when licensed and use allows; external link when there is a url.

    An external link whose address is a PDF also states 'PDF' and the size of the local copy of that document.
    """
    from urllib.parse import urlparse
    from render.common import (actions, card, external_link, file_link, file_size_label, fmt_date, host_file, host_of,
                               link, printed_note, safe_external)
    title = text(item, "title")
    path = item_path(item)
    url = safe_external(text(item, "source_url"))
    use = text(item, "use")
    src = text(item, "outlet") or host_of(url) or "Printed copy"
    local = project_path(path) if path else None
    is_pdf = bool(path) and path.lower().endswith(".pdf")
    links = []
    if local and use != "link" and local.is_file() and licence_for(ctx, path, text(item, "licence_note")):
        rel = host_file(ctx, path)
        if rel:
            fl = file_link(rel, ctx["out"] / rel)
            links.append(fl.replace("<a ", '<a aria-label="%s" ' % esc(title + " (" + re.sub(r"<[^>]+>", "", fl) + ")"), 1))
    if url:
        where = host_of(url) or src
        if urlparse(url).path.lower().endswith(".pdf"):
            size = f", {file_size_label(local)}" if local and local.is_file() else ""
            lab = f"Opens {where} (PDF{size})"
            links.append(link("external", url, lab, f"{lab}: {title}"))
        else:
            links.append(link("external", url, f"Opens {where}", f"Opens {where}: {title}"))
    body = actions(*links) if links else printed_note()
    return card("pdf" if is_pdf else "link", title, src, fmt_date(item.get("date")), "PDF" if is_pdf else "Link", body, level)
