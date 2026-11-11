"""Hidden scenes page (easter egg): a short list of 3D scenes plus one full-screen viewer overlay per scene.

Everything comes from scenes-config.json (repo root): scene facts, camera views from the sidecars, the 20-image gallery
choice and the start view. Facts and labels only, no builder prose. Each scene's .sog is copied to docs/scenes/<id>.sog;
gallery photos and thumbnails are re-encoded from the source JPEGs with every metadata block dropped and published as
docs/scenes/<id>/g01.jpg, t01.jpg and so on, plus start.jpg (the photo the first view matches). PlayCanvas is imported
by assets/scenes.js only when a viewer opens.
"""
import json
import math
import re
from pathlib import Path

from PIL import Image, ImageOps

from render import Page
from render.common import ROOT, card, empty_card, esc, host_of, label, link, project_path

CONFIG_NAME = "scenes-config.json"
FULL_SIDE, THUMB_SIDE = 1600, 400
SOURCE_PREFIX = "Source: "
HEAD_GUARD = (
    "<style>html.sv-pending body{visibility:hidden;background:#0b0d0f}"
    "@media(prefers-reduced-motion:reduce){html.sv-pending body{visibility:visible}}</style>\n"
    "<script>if(/^#[a-z0-9-]+$/.test(location.hash)){var h=document.documentElement;h.classList.add('sv-pending');setTimeout(function(){h.classList.remove('sv-pending')},4000)}</script>\n"
    "<noscript><style>html.sv-pending body{visibility:visible}.scene-controls{display:none}</style></noscript>\n"
)


def load_config():
    """Read scenes-config.json; a missing or broken file gives an empty scene list."""
    try:
        return json.loads((ROOT / CONFIG_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"scenes": []}


def fmt_mb(nbytes):
    """Bytes as '9.0 MB' (always megabytes, one decimal, never below 0.1)."""
    return f"{max(nbytes / (1024 * 1024), 0.1):.1f} MB"


def engine_bytes():
    """Bytes the first load also downloads: the vendored engine."""
    d = ROOT / "vendor" / "playcanvas"
    return sum((d / n).stat().st_size for n in ("playcanvas.js",) if (d / n).is_file())


def fmt_count(value):
    """A figure as text: thousands separators for numbers, 0 when missing."""
    if value is None or value == "":
        return "0"
    if isinstance(value, (int, float)):
        return f"{int(value):,}"
    return str(value)


def save_clean(src, dest, side, quality):
    """Re-encode src as a JPEG whose long side is at most `side`, with no EXIF, XMP, ICC or other metadata.

    Returns (width, height) written, or None when the source cannot be read.
    """
    try:
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            scale = side / max(im.size)
            if scale < 1:
                im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
            clean = Image.new("RGB", im.size)
            clean.paste(im)
            dest.parent.mkdir(parents=True, exist_ok=True)
            clean.save(dest, "JPEG", quality=quality, optimize=True, progressive=True)
            return clean.size
    except OSError:
        return None


def world_view(v):
    """A COLMAP-frame view as the viewer's world frame (the splat entity is turned 180 degrees about Z)."""
    p, f = v["p"], v["f"]
    return {"p": [-p[0], -p[1], p[2]], "f": [-f[0], -f[1], f[2]], "vf": v["vfov"], "a": v["aspect"]}


def build_images(scene, ctx, log):
    """Write the start photo, gallery photos and thumbnails; return the gallery list for the page."""
    sid = scene["id"]
    base = Path(project_path(scene.get("photos_dir", "")))
    out = ctx["out"] / "scenes" / sid
    views = scene["views"]
    start_src = base / views[scene.get("start_view", 0)]["file"]
    size = save_clean(start_src, out / "start.jpg", FULL_SIDE, 82)
    if size is None:
        log(f"scenes: {sid} start photo not readable")
    gallery = []
    for n, g in enumerate(scene.get("gallery", []), start=1):
        src = base / g["file"]
        full = save_clean(src, out / f"g{n:02d}.jpg", FULL_SIDE, 82)
        thumb = save_clean(src, out / f"t{n:02d}.jpg", THUMB_SIDE, 76)
        if not full or not thumb:
            log(f"scenes: {sid} gallery photo {n} skipped (source not readable)")
            continue
        alt = f'{scene.get("facts", {}).get("place", sid.title())}, photo {n} of {len(scene.get("gallery", []))}: {scene.get("alt_subject", "source photo")}{g.get("alt_side", "")}'
        gallery.append({"alt": alt, "v": g["view"], "full": f"scenes/{sid}/g{n:02d}.jpg", "thumb": f"scenes/{sid}/t{n:02d}.jpg",
                        "w": full[0], "h": full[1], "tw": thumb[0], "th": thumb[1], "n": n})
    return gallery, (f"scenes/{sid}/start.jpg" if size else ""), (size or (0, 0))


def figures_html(facts):
    rows = [("Faces Scanned", fmt_count(facts.get("faces_scanned"))), ("Arrests", fmt_count(facts.get("arrests"))),
            ("False Alerts", fmt_count(facts.get("false_alerts")))]
    cells = "".join(f'<div class="sv-fig"><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in rows)
    return f'<dl class="sv-figs">{cells}</dl>'


def when_text(facts):
    parts = [facts.get("date_display", ""), facts.get("time_display", "")]
    return " · ".join(p for p in parts if p)


def viewer_html(ctx, scene, other, gallery, start_rel, start_size=(0, 0)):
    """The static markup of one full-screen viewer (hidden until opened)."""
    sid, facts = scene["id"], scene.get("facts", {})
    title = facts.get("place") or sid.title()
    nav = "".join(f'<li><a data-link="page" href="{esc(s["slug"])}.html">{esc(s["label"])}</a></li>'
                  for s in ctx["config"].get("sections", []))
    switch = (f'<a class="sv-other" href="scenes.html#{esc(other["id"])}" data-scene-link="{esc(other["id"])}">'
              f'Change to: {esc(other["title"])}</a>') if other else ""
    src_text, src_url = facts.get("source_entry_text", ""), facts.get("source_url", "")
    source = ""
    if src_text and src_url:
        host = host_of(src_url)
        kind = " PDF" if src_url.lower().split("#")[0].endswith(".pdf") else ""
        source = link("external", src_url, SOURCE_PREFIX + src_text)
        source = source.replace("<a ", '<a class="sv-source" ', 1).replace(
            "</a>", f'<span class="sv-sr"> (opens {esc(host)}{kind})</span></a>')
    thumbs = "".join(
        f'<li><button type="button" class="sv-thumb" data-gi="{i}" data-src="{esc(g["thumb"])}" data-w="{g["tw"]}" data-h="{g["th"]}" data-alt="{esc(g["alt"])}" aria-label="{esc(g["alt"])}">'
        f'</button></li>' for i, g in enumerate(gallery))
    start_alt = f'{title}, start view: {scene.get("alt_subject", "source photo")}'
    poster = f' data-poster="{esc(start_rel)}" data-poster-alt="{esc(start_alt)}" data-poster-w="{start_size[0]}" data-poster-h="{start_size[1]}"' if start_rel else ""
    return f"""<div class="sv" data-viewer="{esc(sid)}" role="dialog" aria-label="{esc(title)} 3D scene" tabindex="-1" hidden>
<div class="sv-stage" data-role="stage"{poster}></div>
<header class="sv-top">
<nav class="sv-navbar" aria-label="Pages"><ul class="sv-nav">{nav}</ul>{switch}</nav>
<div class="sv-block">
<div class="sv-head">
<div class="sv-title"><h2 class="sv-place">{esc(title)}</h2><p class="sv-when">{esc(when_text(facts))}</p></div>
<button type="button" class="sv-burger" data-role="burger" aria-haspopup="true" aria-expanded="false" aria-controls="sv-menu-{esc(sid)}" aria-label="Menu"><span aria-hidden="true"></span></button>
</div>
{figures_html(facts)}
<ul class="sv-menu" id="sv-menu-{esc(sid)}" data-role="menu" hidden>
<li><button type="button" data-act="reset">Reset view</button></li>
<li><button type="button" data-act="prev">Previous view</button></li>
<li><button type="button" data-act="next">Next view</button></li>
<li><button type="button" data-act="gallery">Gallery</button></li>
</ul>
</div>
</header>
<div class="sv-center" data-role="center">
<p class="sv-hint" data-role="hint" hidden></p>
<progress class="sv-progress" data-role="bar" max="100" aria-label="Loading {esc(title)}" hidden></progress>
<p class="sv-msg" data-role="msg" role="status" aria-live="polite"></p>
<button type="button" class="sv-retry" data-act="retry" hidden>Retry</button>
</div>
<footer class="sv-bottom">
{source}
</footer>
<div class="sv-gallery" data-role="gallery" role="dialog" aria-label="Gallery" tabindex="-1" hidden>
<div class="sv-gal-bar"><h3>Gallery</h3><button type="button" class="sv-x" data-act="gallery-close" aria-label="Close gallery">&times;</button></div>
<ul class="sv-grid">{thumbs}</ul>
<div class="sv-lightbox" data-role="lightbox" role="dialog" aria-label="Photo" tabindex="-1" hidden>
<div class="sv-lb-bar"><span data-role="lb-count"></span>
<button type="button" class="sv-go" data-act="lb-go">Go to this view</button>
<button type="button" class="sv-x" data-act="lb-close" aria-label="Close photo">&times;</button></div>
<div class="sv-lb-main"><button type="button" class="sv-lb-nav" data-act="lb-prev" aria-label="Previous photo">&lsaquo;</button>
<div class="sv-lb-slot" data-role="lb-slot"></div>
<button type="button" class="sv-lb-nav" data-act="lb-next" aria-label="Next photo">&rsaquo;</button></div>
</div>
</div>
</div>
"""


def render(ctx):
    log = ctx.get("log", print)
    lab = label(ctx, "scenes")
    cfg = load_config()
    scenes = [s for s in cfg.get("scenes", []) if isinstance(s, dict) and re.fullmatch(r"[a-z0-9-]+", str(s.get("id", "")))]
    eng = engine_bytes()
    cards, viewers, data = [], [], []
    for s in scenes:
        sid = s["id"]
        facts = s.get("facts", {})
        title = facts.get("place") or sid.title()
        rel = None
        if s.get("sog") and project_path(s["sog"]).is_file() and s.get("views"):
            rel = ctx["copy_asset"](s["sog"], f"scenes/{sid}.sog")
        if not rel:
            log(f"scenes: {sid} has no usable .sog source or views; showing 'On its way'")
            cards.append(empty_card(title, attrs=f'data-scene="{esc(sid)}"'))
            continue
        sog_bytes = (ctx["out"] / rel).stat().st_size
        gallery, start_rel, start_size = build_images(s, ctx, log)
        others = [o for o in scenes if o["id"] != sid and o.get("sog")]
        other = ({"id": others[0]["id"], "title": others[0].get("facts", {}).get("place") or others[0]["id"].title()}
                 if others else None)
        viewers.append(viewer_html(ctx, s, other, gallery, start_rel, start_size))
        data.append({"id": sid, "title": title, "sog": rel, "sogBytes": sog_bytes, "engineBytes": eng,
                     "start": s.get("start_view", 0), "scale": s.get("world_scale", 10),
                     "views": [world_view(v) for v in s["views"]], "gallery": gallery})
        body = (f'<div class="scene-controls"><button type="button" class="scene-btn" data-action="load">'
                f'Load 3D scene ({esc(fmt_mb(sog_bytes + eng))})</button></div>'
                '<noscript><p class="scene-nojs">Needs JavaScript</p></noscript>\n')
        cards.append(card("section", title, "Jared Krauss", facts.get("date_display", ""), "3D scene",
                          body, attrs=f'data-scene="{esc(sid)}"'))
    page = '<div class="scenes-grid">\n' + "\n".join(cards) + "\n</div>\n"
    page += '<p class="scenes-home">' + link("page", "index.html", "Home") + "</p>\n"
    payload = json.dumps({"scenes": data}, separators=(",", ":")).replace("</", "<\\/")
    page += f'<script type="application/json" id="scenes-data">{payload}</script>\n' + "\n".join(viewers)
    head = '<link rel="stylesheet" href="assets/scenes.css">\n' + HEAD_GUARD
    scripts = '<script type="module" src="assets/scenes.js"></script>'
    return Page("scenes", lab, lab, page, head_extra=head, scripts_extra=scripts, in_nav=False, noindex=True)
