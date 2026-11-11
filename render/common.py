"""Shared helpers for every page module. Facts only: no prose is generated here."""
import html
import re
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
EMPTY_TEXT = "On its way"
PRINTED_TEXT = "Printed copy at the talk"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
INTERNAL_URL = re.compile(
    r"(localhost|127\.\d+\.\d+\.\d+|\b10\.\d+\.\d+\.\d+|192\.168\.|\b100\.\d+\.\d+\.\d+|\.ts\.net|tailscale|\.local\b|\.internal\b|:878[78]\b)",
    re.I)


def esc(value):
    """HTML-escape any value (None becomes an empty string)."""
    return html.escape("" if value is None else str(value), quote=True)


def text(item, key):
    """A stripped string field from a selections item, or ''."""
    v = item.get(key) if isinstance(item, dict) else None
    return v.strip() if isinstance(v, str) else ""


def fmt_date(value):
    """'2017-03-12' (or a datetime string) -> '12 Mar 2017'; anything unparseable -> 'Undated'."""
    v = value.strip() if isinstance(value, str) else ""
    if not v:
        return "Undated"
    for fmt, cand in (("%Y-%m-%d", v[:10]), ("%d/%m/%Y", v), ("%d %b %Y", v), ("%d %B %Y", v)):
        try:
            d = datetime.strptime(cand, fmt)
            return f"{d.day} {MONTHS[d.month - 1]} {d.year}"
        except ValueError:
            continue
    return "Undated"


_FULL_DATE = re.compile(r"\b(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* (\d{4})\b")
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_MONTH_YEAR = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* (\d{4})\b")
_YEAR_LEAD = re.compile(r"^(?:[A-Za-z]+ )?(\d{4})\b")


def date_from_facts(value):
    """A date taken from a free-text fact string such as '23 August 2017' -> '23 Aug 2017'; '' when none is stated."""
    v = value.strip() if isinstance(value, str) else ""
    if not v or re.match(r"(not printed|PDF created|latest press item)", v, re.I):
        return ""
    m = _ISO_DATE.search(v)
    if m:
        return fmt_date(m.group(0))
    m = _FULL_DATE.search(v)
    if m:
        return f"{int(m.group(1))} {m.group(2)} {m.group(3)}"
    m = _MONTH_YEAR.match(v)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    m = _YEAR_LEAD.match(v)
    return m.group(1) if m else ""


def item_date(item):
    """Date label for a card: top-level date, else the date in mla_facts, else 'Undated'."""
    d = fmt_date(item.get("date")) if isinstance(item, dict) else "Undated"
    if d != "Undated":
        return d
    facts = item.get("mla_facts") if isinstance(item, dict) else None
    if isinstance(facts, dict):
        facts = facts.get("date")
    return date_from_facts(facts) or "Undated"


def licence_line(*notes):
    """The real licence named in a licence_note (starts with 'CC' or 'Open Government'), up to the first full stop; else ''."""
    for n in notes:
        n = (n or "").strip()
        if re.match(r"(CC\b|Open Government)", n):
            m = re.search(r"\.(?:\s|$)| \(", n)
            return (n[:m.start()] if m else n).strip()
    return ""


def licence_html(*notes):
    line = licence_line(*notes)
    return f'<p class="card-licence">{esc(line)}</p>\n' if line else ""


def whole_file_for(ctx, path):
    """The whole_files row with the same source path, or None."""
    key = norm_path(path)
    if not key:
        return None
    for row in ctx["sel"].get("whole_files", []):
        if isinstance(row, dict) and norm_path(item_path(row)) == key:
            return row
    return None


def poster_facts(ctx, p):
    """(source, date, licence html) for a poster, from its own fields and the whole_files row of the same PDF."""
    row = whole_file_for(ctx, item_path(p)) or {}
    source = (text(row, "title") or host_of(safe_external(text(p, "source_url")))
              or host_of(safe_external(text(row, "source_url"))) or "Printed copy")
    d = item_date(p)
    if d == "Undated" and row:
        d = item_date(row)
    return source, d, licence_html(text(p, "licence_note"), text(row, "licence_note"))


def in_group_sections(ctx, rows, make_card):
    """Card html for rows, in <section> blocks under an h2 per `group` (first-seen order), ungrouped rows last without a heading."""
    groups, order, loose = {}, [], []
    for r in rows:
        g = text(r, "group")
        if g:
            if g not in groups:
                groups[g] = []
                order.append(g)
            groups[g].append(r)
        else:
            loose.append(r)
    if not order:
        return cards_wrap([make_card(r, 2) for r in rows])
    out = []
    for n, g in enumerate(order):
        out.append(f'<section class="card-group" aria-labelledby="group-{n}">\n<h2 id="group-{n}" class="group-title">{esc(g)}</h2>\n'
                   + cards_wrap([make_card(r, 3) for r in groups[g]]) + "\n</section>")
    if loose:
        out.append(cards_wrap([make_card(r, 2) for r in loose]))
    return "\n".join(out)


def whole_file_rows(ctx, slug):
    """whole_files rows for the Documents (use host/link) or Handouts (use print, or 'print' in also) page."""
    rows = [w for w in ctx["sel"].get("whole_files", []) if isinstance(w, dict)]
    if slug == "handouts":
        return [w for w in rows if text(w, "use") == "print" or "print" in (w.get("also") or [])]
    return [w for w in rows if text(w, "use") in ("host", "link")]


def file_size_label(path):
    """'15.4 KB' or '1.2 MB' for a file on disk."""
    size = Path(path).stat().st_size
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def project_path(p):
    """Resolve a selections/config path: absolute stays, relative is from the project root."""
    pp = Path(str(p))
    return pp if pp.is_absolute() else ROOT / pp


def norm_path(p):
    """Normalised key for comparing paths: forward slashes, lower case, project-relative when inside the project."""
    s = str(p or "").strip().replace("\\", "/")
    if not s:
        return ""
    try:
        pp = Path(s)
        if pp.is_absolute():
            s = pp.resolve().relative_to(ROOT.resolve()).as_posix()
    except (ValueError, OSError):
        pass
    while s.startswith("./"):
        s = s[2:]
    return s.lower()


def item_path(item):
    """The source file path of a selections item (accepts source_path, path, url_or_path)."""
    for k in ("source_path", "path", "url_or_path"):
        v = text(item, k)
        if v:
            return v
    return ""


def host_of(url):
    """Host name of a URL without 'www.', or ''."""
    try:
        h = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def safe_external(url):
    """Return url if it is a public http(s) address, else '' (rule 7: internal addresses never published)."""
    u = (url or "").strip()
    if not re.match(r"https?://[^/\s]+", u, re.I) or INTERNAL_URL.search(u):
        return ""
    return u


def licence_for(ctx, path, own_note=""):
    """Licence lookup (SPEC): own note, else a whole_files row with a note, else config licence_map, else ''."""
    if (own_note or "").strip():
        return own_note.strip()
    key = norm_path(path)
    if not key:
        return ""
    for row in ctx["sel"].get("whole_files", []):
        if norm_path(item_path(row)) == key and text(row, "licence_note"):
            return text(row, "licence_note")
    for k, v in (ctx["config"].get("licence_map") or {}).items():
        if norm_path(k) == key and isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def photo_cleared(ctx, path):
    """True when a photo path is listed in config photos_cleared."""
    key = norm_path(path)
    return bool(key) and key in {norm_path(p) for p in ctx["config"].get("photos_cleared") or []}


class AssetRefused(Exception):
    pass


def _check_copy(src, dest_rel):
    s = Path(src)
    if not s.is_file():
        raise AssetRefused("source file not found")
    if any(part.lower() == "renders" for part in s.parts):
        raise AssetRefused("source is under a renders folder (rule 9)")
    d = str(dest_rel).replace("\\", "/")
    if not d or d.startswith("/") or ".." in d.split("/") or re.match(r"^[A-Za-z]:", d) or "file:" in d.lower():
        raise AssetRefused("destination is not a clean relative path")
    return s, d


def make_copy_asset(out, log):
    """Build ctx['copy_asset']: copy src into out/dest_rel and return dest_rel; returns None (and logs) when refused."""
    def copy_asset(src, dest_rel):
        try:
            s, d = _check_copy(project_path(src), dest_rel)
        except AssetRefused as e:
            log(f"asset refused ({Path(str(src)).name}): {e}")
            return None
        target = Path(out) / d
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, target)
        return d
    return copy_asset


def host_file(ctx, src, subdir="files"):
    """Copy a source file into out/<subdir>/ with a clean unique name; returns the relative url or None."""
    key = norm_path(src)
    cache = ctx.setdefault("_hosted", {})
    if key in cache:
        return cache[key]
    p = project_path(src)
    stem = re.sub(r"[^a-z0-9]+", "-", p.stem.lower()).strip("-") or "file"
    name, n = f"{stem}{p.suffix.lower()}", 2
    while any(v == f"{subdir}/{name}" for v in cache.values()):
        name, n = f"{stem}-{n}{p.suffix.lower()}", n + 1
    rel = ctx["copy_asset"](p, f"{subdir}/{name}")
    cache[key] = rel
    return rel


def link(kind, href, label, aria_label=""):
    """An anchor of one of the three link kinds: page | file | external."""
    attrs = f'data-link="{esc(kind)}" href="{esc(href)}"'
    if kind == "external":
        attrs += ' rel="noopener"'
    if aria_label:
        attrs += f' aria-label="{esc(aria_label)}"'
    return f"<a {attrs}>{esc(label)}</a>"


def external_link(url, source):
    """External link whose text says where it opens."""
    return link("external", url, f"Opens {source}")


def file_link(rel, path):
    """File link whose text states type and size, e.g. 'PDF, 0.2 MB'."""
    ext = Path(rel).suffix.lstrip(".").upper() or "File"
    return link("file", rel, f"{ext}, {file_size_label(path)}")


def card(kind, title, source, date, badge, body="", level=2, attrs=""):
    """The one card pattern: title, then meta (source, date, badge), then body html."""
    h = f"h{level}"
    extra = (" " + attrs) if attrs else ""
    return (f'<article class="card" data-kind="{esc(kind)}"{extra}>\n'
            f'<{h} class="card-title">{esc(title)}</{h}>\n'
            f'<p class="card-meta"><span class="source">{esc(source)}</span>'
            f'<span class="date">{esc(date)}</span><span class="card-kind">{esc(badge)}</span></p>\n'
            f'{body}</article>')


def empty_card(title, level=2, attrs=""):
    """Dashed 'On its way' card with a title."""
    h = f"h{level}"
    extra = (" " + attrs) if attrs else ""
    return (f'<article class="card card--empty" data-kind="empty"{extra}>\n'
            f'<{h} class="card-title">{esc(title)}</{h}>\n'
            f'<p class="card-empty-text">{EMPTY_TEXT}</p>\n</article>')


def empty_state(label):
    """A whole section's empty state: one 'On its way' card titled with the section label."""
    return cards_wrap([empty_card(label)])


def printed_note():
    return f'<p class="card-note">{PRINTED_TEXT}</p>\n'


def actions(*links):
    links = [x for x in links if x]
    return f'<div class="card-actions">{"".join(links)}</div>\n' if links else ""


def cards_wrap(cards):
    return '<div class="cards">\n' + "\n".join(cards) + "\n</div>"


def whole_file_card(ctx, item, level=2):
    """Card for a whole_files row: hosted file if licensed (and use allows), external link if it has a url, else printed note."""
    title = text(item, "title")
    path = item_path(item)
    url = safe_external(text(item, "source_url"))
    use = text(item, "use")
    src = text(item, "outlet") or host_of(url) or "Printed copy"
    date = item_date(item)
    kind = "pdf" if path.lower().endswith(".pdf") else "link"
    badge = "PDF" if kind == "pdf" else "Link"
    links = []
    if path and use != "link" and licence_for(ctx, path, text(item, "licence_note")) and project_path(path).is_file():
        rel = host_file(ctx, path)
        if rel:
            links.append(file_link(rel, ctx["out"] / rel))
    if url:
        links.append(external_link(url, host_of(url) or src))
    body = actions(*links) if links else printed_note()
    return card(kind, title, src, date, badge, body, level)


def sel_items(ctx, key):
    return ctx["sel"].get(key, [])


def slideshow_items(ctx):
    """Slideshow entries: config slideshow.items, else the figures in number order, charts not already figures, cleared photos, video splats."""
    cfg = (ctx["config"].get("slideshow") or {}).get("items") or []
    if cfg:
        return [{"kind": text(i, "kind") or "item", "ref": text(i, "ref"), "label": text(i, "ref")} for i in cfg if isinstance(i, dict)]
    from render.media import figures
    figs = figures(ctx)
    out = [{"kind": "figure", "ref": str(f["n"]), "label": f["title"]} for f in figs]
    numbered = {f["id"] for f in figs if f["kind"] == "chart"}
    out += [{"kind": "chart", "ref": text(c, "id"), "label": text(c, "id")} for c in sel_items(ctx, "charts_ready")
            if text(c, "id") not in numbered]
    for ph in sel_items(ctx, "photos"):
        if photo_cleared(ctx, item_path(ph)):
            out.append({"kind": "photo", "ref": item_path(ph), "label": text(ph, "caption") or text(ph, "title") or "Photo"})
    for s in sel_items(ctx, "splats"):
        if item_path(s).lower().endswith((".mp4", ".webm")):
            out.append({"kind": "video", "ref": item_path(s), "label": text(s, "title") or "Video"})
    return out


def count_for(ctx, slug):
    """Default item count shown on the Home card for a section (a module may expose count(ctx) instead)."""
    if slug == "slideshow":
        return len(slideshow_items(ctx))
    return 0


def count_label(n):
    return f"{n} item" + ("" if n == 1 else "s")


def label(ctx, slug):
    """Section or hidden-page label from config."""
    for s in list(ctx["config"].get("sections", [])) + list(ctx["config"].get("hidden_pages", [])):
        if s.get("slug") == slug:
            return s.get("label", slug)
    return slug


def simple_page(ctx, slug, cards):
    """Wrap a list of card html (or the empty state) into a Page with the config label as title and h1."""
    from render import Page
    lab = label(ctx, slug)
    return Page(slug, lab, lab, cards_wrap(cards) if cards else empty_state(lab))



def rows_page(ctx, slug, make_card):
    """Page for a whole_files-backed section: grouped cards, or the empty state."""
    from render import Page
    lab = label(ctx, slug)
    rows = whole_file_rows(ctx, slug)
    return Page(slug, lab, lab, in_group_sections(ctx, rows, make_card) if rows else empty_state(lab))
