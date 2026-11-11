"""Hidden scenes page (easter egg): one card per configured splat scene, loaded only on a tap.

Facts only: titles from config, sizes computed from the copied files, date parsed from the source file name,
control labels. The .sog files are copied to docs/scenes/<id>.sog; PlayCanvas (vendor/playcanvas/*.js) is
downloaded and imported by assets/scenes.js after the first tap.
"""
import re
from pathlib import Path

from render import Page
from render.common import ROOT, card, empty_card, esc, fmt_date, label, link, project_path

NOSCRIPT_STYLE = "<noscript><style>.scene-controls{display:none}</style></noscript>"
SOURCE_NAME = "Jared Krauss"


def fmt_mb(nbytes):
    """Bytes as '9.0 MB' (always megabytes, one decimal, never below 0.1)."""
    return f"{max(nbytes / (1024 * 1024), 0.1):.1f} MB"


def engine_bytes():
    """Bytes the first load also downloads: the vendored engine and camera script."""
    d = ROOT / "vendor" / "playcanvas"
    return sum((d / n).stat().st_size for n in ("playcanvas.js", "camera-controls.js") if (d / n).is_file())


def date_from_name(src):
    """'2026-10-26_...sog' -> '26 Oct 2026'; no leading date -> 'Undated'."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", Path(str(src)).name)
    return fmt_date(m.group(1) if m else "")


def scene_body(sog_bytes):
    """Controls, status line, hint and empty stage for one scene."""
    eng = engine_bytes()
    first = f"Load 3D scene ({fmt_mb(sog_bytes + eng)})"
    later = f"Load 3D scene ({fmt_mb(sog_bytes)})"
    return f"""<div class="scene-controls">
<button type="button" class="scene-btn" data-action="load" data-sog-label="{esc(later)}">{esc(first)}</button>
<button type="button" class="scene-btn" data-action="close" hidden>Close 3D scene</button>
<button type="button" class="scene-btn" data-action="retry" hidden>Retry</button>
<button type="button" class="scene-btn" data-action="reset" disabled>Reset view</button>
</div>
<p class="scene-hint" data-role="hint" hidden></p>
<p class="scene-msg" data-role="msg" role="status" aria-live="polite"></p>
<div class="scene-stage" data-role="stage" hidden></div>
<noscript><p class="scene-nojs">Needs JavaScript</p></noscript>
"""


def render(ctx):
    lab = label(ctx, "scenes")
    cards = []
    for s in ctx["config"].get("splat_scenes", []) or []:
        if not isinstance(s, dict):
            continue
        sid = re.sub(r"[^a-z0-9-]+", "-", str(s.get("id", "")).lower()).strip("-")
        title = s.get("title") or sid
        if not sid:
            continue
        src = s.get("source", "")
        rel = None
        if src and project_path(src).is_file():
            rel = ctx["copy_asset"](src, f"scenes/{sid}.sog")
        if not rel:
            ctx.get("log", print)(f"scenes: {sid} has no usable .sog source; showing 'On its way'")
            cards.append(empty_card(title, attrs=f'data-scene="{esc(sid)}"'))
            continue
        sog_bytes = (ctx["out"] / rel).stat().st_size
        attrs = (f'data-scene="{esc(sid)}" data-src="{esc(rel)}" data-title="{esc(title)}" '
                 f'data-sog-bytes="{sog_bytes}" data-engine-bytes="{engine_bytes()}"')
        cards.append(card("section", title, SOURCE_NAME, date_from_name(src), "3D scene",
                          scene_body(sog_bytes), attrs=attrs))
    body = '<div class="scenes-grid">\n' + "\n".join(cards) + "\n</div>\n"
    body += '<p class="scenes-home">' + link("page", "index.html", "Home") + "</p>"
    head = '<link rel="stylesheet" href="assets/scenes.css">\n' + NOSCRIPT_STYLE
    scripts = '<script type="module" src="assets/scenes.js"></script>'
    return Page("scenes", lab, lab, body, head_extra=head, scripts_extra=scripts, in_nav=False, noindex=True)
