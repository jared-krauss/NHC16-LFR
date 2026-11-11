"""Bibliography page: one skimmable entry per public source (hosted or linked), with its MLA citation.

Entries come from selections whole_files (use host/link) and news, matched to the shared MLA records
(config citations_path, formatted by tools/mla-citations/mla.py), plus the Met deployment records used by the
3D scenes (config scene_documents + scene_facts_path). One entry per document: de-duplicated by citation id.
Display titles: title-overrides.json (file name or URL -> title), else the citation title, else the selection title.
Thumbnails come from the thumbs index; entries without one get a typographic tile.
"""
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

from render import Page
from render.common import (MONTHS, actions, empty_state, esc, file_size_label, fmt_date, host_file, host_of, item_date,
                           item_path, label, licence_for, licence_html, link, norm_path, project_path, safe_external,
                           text)

THUMB_MAX_W = 240
SKIP_WORDS = {"the", "of", "and", "a", "an", "for", "on", "in"}


def _read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _tools(ctx):
    """(selections_to_citations module, mla module, mla config) or (None, None, None) when unavailable."""
    if "_mla" not in ctx:
        ctx["_mla"] = (None, None, None)
        d = ctx["config"].get("mla_tools_dir")
        try:
            if d and Path(d).is_dir():
                if d not in sys.path:
                    sys.path.insert(0, d)
                import mla
                import selections_to_citations as stc
                ctx["_mla"] = (stc, mla, mla.load_types(mla.DEFAULT_TYPES))
        except Exception as e:
            ctx["log"](f"bibliography: MLA tools unavailable ({type(e).__name__}: {e}); entries shown without citations")
    return ctx["_mla"]


def _overrides(ctx):
    p = ctx["config"].get("title_overrides")
    data = _read(ctx["root"] / p) if p else None
    return data if isinstance(data, dict) else {}


def _override_for(ov, path, url):
    for key in (url, Path(str(path or "")).name if path else ""):
        if key and key in ov:
            return ov[key]
    return ""


def _find_citation(stc, cits, idx, url, title):
    """The citation record for a selections row: by address or DOI, else by cleaned title."""
    m = idx.find(url, title)
    if m:
        return m
    wanted = stc.norm_title(title)
    for c in cits:
        ct = stc.norm_title(c.get("title"))
        if ct and (ct == wanted or (len(ct) > 12 and ct in wanted)):
            return c
    return None


def _names(c):
    out = []
    for a in c.get("authors") or c.get("author") or []:
        if isinstance(a, dict):
            out.append(a.get("org") or a.get("family") or "")
    return [n for n in out if n]


def _author_line(c, fallback):
    names = _names(c)
    people = [a for a in (c.get("authors") or []) if isinstance(a, dict) and a.get("given")]
    if len(names) == 1 and people:
        return people[0]["given"] + " " + people[0]["family"]
    if len(names) > 2:
        return names[0] + " et al."
    if names:
        return " & ".join(names)
    return fallback


def _date_parts(iso):
    """(sort key, display) for a citation date 'YYYY[-MM[-DD]]'."""
    m = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", iso or "")
    if not m:
        return "9999", "Undated"
    y, mo, d = m.groups()
    key = y + "-" + (mo or "00") + "-" + (d or "00")
    if d:
        return key, fmt_date(f"{y}-{mo}-{d}")
    if mo:
        return key, f"{MONTHS[int(mo) - 1]} {y}"
    return key, y


def _initials(name):
    words = [w for w in re.split(r"[^A-Za-z0-9]+", name or "") if w and w.lower() not in SKIP_WORDS]
    s = "".join(w[0].upper() for w in words[:3])
    return s or "?"


def _hue(name):
    return int(hashlib.sha1((name or "").encode("utf-8")).hexdigest()[:4], 16) % 360


def _thumb(ctx, key_candidates, entry_id):
    """Copy a thumbnail from the thumbs index into the site; (rel, w, h) or None."""
    idx = ctx.setdefault("_thumbs_idx", None)
    if idx is None:
        p = ctx["config"].get("thumbs_index")
        data = _read(p) if p and Path(p).is_file() else None
        idx = {norm_path(k): v for k, v in (data or {}).items()} if isinstance(data, dict) else {}
        ctx["_thumbs_idx"] = idx
    for k in key_candidates:
        v = idx.get(norm_path(k)) if k else None
        if isinstance(v, dict):
            v = v.get("thumb") or v.get("file") or v.get("path")
        if v and Path(v).is_file():
            rel = ctx["copy_asset"](v, f"bib/{entry_id}{Path(v).suffix.lower()}")
            if rel:
                try:
                    from PIL import Image
                    dest = ctx["out"] / rel
                    os.chmod(dest, stat.S_IWRITE)
                    with Image.open(dest) as im:
                        im.load()
                        if im.size[0] > THUMB_MAX_W:
                            im = im.convert("RGB")
                            im.thumbnail((THUMB_MAX_W, THUMB_MAX_W * 2))
                            im.save(dest, quality=80)
                        return rel, im.size[0], im.size[1]
                except Exception:
                    return None
    return None


def _group_for(cfg, e):
    ov = cfg.get("group_overrides") or {}
    if e["id"] in ov:
        return ov[e["id"]]
    for rule in cfg.get("rules", []):
        ok = True
        if "source_list" in rule:
            ok = ok and bool(set(rule["source_list"]) & e["source_lists"])
        if "type" in rule:
            ok = ok and e["type"] in rule["type"]
        if "selection_group" in rule:
            ok = ok and e["selection_group"] in rule["selection_group"]
        if ok:
            return rule["group"]
    return (cfg.get("groups") or [{"id": "other"}])[-1]["id"]


def _entry(ctx, base, cit, ov, tools_cfg):
    """Fill the display fields of one entry from a base dict (selection facts) and an optional citation record."""
    title = _override_for(ov, base.get("path"), base.get("url")) or (cit or {}).get("title") or base["title"]
    cit_date = (cit or {}).get("date") or base.get("iso_date") or ""
    key, disp = _date_parts(cit_date)
    outlet = base.get("outlet") or host_of(base.get("url") or "")
    cont = (cit or {}).get("container") or ""
    publisher = (cit or {}).get("publisher") or ""
    author = _author_line(cit or {}, publisher or cont or outlet or "")
    pub = ""
    for cand in (cont, publisher, outlet):
        if cand and cand.lower() not in author.lower() and author.lower() not in cand.lower():
            pub = cand
            break
    base.update(title=title, author=author or "Author not stated", pub=pub, date_key=key, date_disp=disp,
                type=(cit or {}).get("type") or base.get("type") or "")
    base["cit"] = cit
    return base


def _mla_html(ctx, entries):
    """Fill mla_html on entries that have a citation record; never shows missing-field markers."""
    stc, mla, cfg = _tools(ctx)
    if not mla:
        return
    items = []
    for e in entries:
        if e.get("cit"):
            rec = dict(e["cit"])
            rec["title"] = e["title"]
            rec["id"] = e["id"]
            items.append(rec)
    try:
        built = mla.build_entries(items, cfg, "html", False)
    except Exception as ex:
        ctx["log"](f"bibliography: citation formatting failed ({type(ex).__name__}: {ex})")
        return
    by = {it["id"]: txt for it, txt, _p in built}
    for e in entries:
        t = by.get(e["id"], "")
        t = re.sub(r"</?a\b[^>]*>", "", t)
        if t and "[MISSING" not in t and "None" not in t:
            e["mla_html"] = t


def _load(ctx):
    if "_bib" in ctx:
        return ctx["_bib"]
    cfg = ctx["config"].get("bibliography") or {}
    stc, mla, _mc = _tools(ctx)
    cp = ctx["config"].get("citations_path")
    cits = _read(cp) if cp and Path(cp).is_file() else None
    cits = cits if isinstance(cits, list) else []
    idx = stc.ExistingIndex(cits, stc.read_json(stc.DEFAULT_CONFIG)) if (stc and cits) else None
    ov = _overrides(ctx)
    by_id, order = {}, []

    def add(base, cit):
        eid = (cit or {}).get("id") or base["id"]
        base["id"] = eid
        if eid in by_id:
            by_id[eid]["source_lists"] |= base["source_lists"]
            return
        by_id[eid] = _entry(ctx, base, cit, ov, None)
        order.append(eid)

    def match(url, title):
        return _find_citation(stc, cits, idx, url, title) if idx else None

    def slug(t):
        return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:60] or "source"

    for w in ctx["sel"].get("whole_files", []):
        if text(w, "use") not in ("host", "link"):
            continue
        url = safe_external(text(w, "source_url"))
        path = item_path(w)
        base = {"title": text(w, "title"), "path": path, "url": url, "outlet": text(w, "outlet"),
                "iso_date": text(w, "date"), "source_lists": {"whole_files"},
                "selection_group": text(w, "group"), "use": text(w, "use"), "licence_note": text(w, "licence_note"),
                "thumb_keys": [path], "id": slug(text(w, "title"))}
        add(base, match(url, text(w, "title")))
    for n in ctx["sel"].get("news", []):
        url = safe_external(text(n, "url"))
        base = {"title": text(n, "title"), "path": "", "url": url, "outlet": text(n, "outlet"),
                "iso_date": text(n, "date"), "source_lists": {"news"}, "selection_group": "", "use": "link",
                "licence_note": "", "thumb_keys": [url], "id": slug(text(n, "title")),
                "type": "web_page" if text(n, "kind").lower() == "commentary" else "news_article",
                "kind_label": "Commentary" if text(n, "kind").lower() == "commentary" else ""}
        add(base, match(url, text(n, "title")))

    facts = _read(ctx["config"].get("scene_facts_path") or "") if ctx["config"].get("scene_facts_path") else None
    for sd in ctx["config"].get("scene_documents", []):
        f = (facts or {}).get(sd["scene"]) if isinstance(facts, dict) else None
        if not isinstance(f, dict) or not f.get("source_doc_title"):
            continue
        url = safe_external(f.get("source_url") or "")
        eid = sd["id"]
        base = {"id": eid, "title": f["source_doc_title"], "path": "", "url": url, "outlet": sd.get("publisher", ""),
                "iso_date": "", "source_lists": {"scenes"}, "selection_group": "", "use": "link", "licence_note": "",
                "thumb_keys": [], "type": "report_gov", "pages": [f.get("source_page")] if f.get("source_page") else []}
        e = _entry(ctx, base, None, ov, None)
        e["author"] = sd.get("publisher", "") or e["author"]
        e["pub"] = ""
        e["group_forced"] = sd.get("group")
        by_id[eid] = e
        order.append(eid)

    entries = [by_id[i] for i in order]
    _mla_html(ctx, entries)
    labels = cfg.get("type_labels") or {}
    groups = {g["id"]: [] for g in cfg.get("groups", [])}
    for e in entries:
        e["group"] = e.pop("group_forced", None) or _group_for(cfg, e)
        e["badge"] = e.get("kind_label") or labels.get(e["type"], "Source")
        e["hosted"] = None
        if e["use"] == "host" and e["path"] and project_path(e["path"]).is_file() and \
                licence_for(ctx, e["path"], e.get("licence_note", "")):
            e["hosted"] = host_file(ctx, e["path"])
        e["thumb"] = _thumb(ctx, e["thumb_keys"], re.sub(r"[^a-z0-9-]", "-", e["id"].lower())) if e["thumb_keys"] else None
        groups.setdefault(e["group"], []).append(e)
    for g in groups.values():
        g.sort(key=lambda e: (e["date_key"], e["title"].lower()))
    ctx["_bib"] = {"entries": entries, "groups": groups, "by_id": by_id}
    return ctx["_bib"]


def entry_title(ctx, source_id, fallback=""):
    """The one display title for a source id (used by Media and the Slideshow), else the fallback."""
    e = _load(ctx)["by_id"].get(source_id)
    return e["title"] if e else fallback


def entry_date(ctx, source_id):
    e = _load(ctx)["by_id"].get(source_id)
    return e["date_disp"] if e else "Undated"


def has_entry(ctx, source_id):
    return source_id in _load(ctx)["by_id"]


def count(ctx):
    return len(_load(ctx)["entries"])


def _media_pages(ctx, eid):
    try:
        from render.media import figures
        return [(f["n"], f["printed_page"]) for f in figures(ctx) if f["source_id"] == eid]
    except Exception:
        return []


def _thumb_html(e, href, aria, kind):
    if e["thumb"]:
        rel, w, h = e["thumb"]
        inner = f'<img src="{esc(rel)}" width="{w}" height="{h}" alt="" loading="lazy">'
    else:
        name = e["pub"] or e["author"]
        inner = (f'<span class="bib-tile" style="--hue:{_hue(name)}" aria-hidden="true">{esc(_initials(name))}</span>')
    if not href:
        return f'<div class="bib-thumb">{inner}</div>'
    ext = ' rel="noopener"' if kind == "external" else ""
    return (f'<a class="bib-thumb" data-link="{kind}" href="{esc(href)}"{ext} aria-label="{esc(aria)}" '
            f'tabindex="-1">{inner}</a>')


def _ext_label(e, host):
    """'Opens host' (adding '(PDF, size)' when the address is a PDF and a local copy gives the size)."""
    from urllib.parse import urlparse
    if not urlparse(e["url"]).path.lower().endswith(".pdf"):
        return f"Opens {host}"
    local = project_path(e["path"]) if e.get("path") else None
    size = f", {file_size_label(local)}" if local and local.is_file() else ""
    return f"Opens {host} (PDF{size})"


def _entry_html(ctx, e):
    title = e["title"]
    href, kind, aria, acts, note = "", "", "", [], ""
    if e["hosted"]:
        size = file_size_label(ctx["out"] / e["hosted"])
        ext = Path(e["hosted"]).suffix.lstrip(".").upper() or "File"
        href, kind = e["hosted"], "file"
        aria = f"{title} ({ext}, {size})"
        acts.append(link("file", href, f"{ext}, {size}", aria))
        if e["url"]:
            lab = _ext_label(e, host_of(e["url"]))
            acts.append(link("external", e["url"], lab, f"{lab}: {title}"))
    elif e["url"]:
        href, kind = e["url"], "external"
        lab = _ext_label(e, host_of(e["url"]))
        aria = f"{title} ({lab[0].lower() + lab[1:]})"
        acts.append(link("external", e["url"], lab, f"{lab}: {title}"))
    else:
        note = '<p class="card-note">Printed copy at the talk</p>\n'
    if href:
        ext_attr = ' rel="noopener"' if kind == "external" else ""
        h = (f'<a data-link="{kind}" href="{esc(href)}"{ext_attr} aria-label="{esc(aria)}">{esc(title)}</a>')
    else:
        h = esc(title)
    xrefs = ""
    figs = _media_pages(ctx, e["id"])
    bits = []
    if figs:
        bits = [link("page", f"media.html#fig-{n}", f"Fig. {n}, p. {p}") for n, p in figs]
    for pg in e.get("pages") or []:
        xrefs += f'<p class="bib-pages"><small>Entry on p. {esc(pg)}</small></p>\n'
    if bits:
        xrefs += '<p class="bib-pages"><small>Figures from this document: ' + " ".join(bits) + "</small></p>\n"
    cite = f'<p class="bib-cite"><small>{e["mla_html"]}</small></p>\n' if e.get("mla_html") else ""
    pub = f'<span class="bib-pub">{esc(e["pub"])}</span>' if e["pub"] else ""
    return (f'<article class="card bib-entry" id="{esc(e["id"])}" data-kind="{"pdf" if e["hosted"] else "link"}">\n'
            + _thumb_html(e, href, aria, kind) + '\n<div class="bib-body">\n'
            f'<h3 class="card-title bib-title">{h}</h3>\n'
            f'<p class="card-meta"><span class="source"><strong class="bib-author">{esc(e["author"])}</strong>{pub}</span>'
            f'<span class="date">{esc(e["date_disp"])}</span><span class="card-kind">{esc(e["badge"])}</span></p>\n'
            + cite + xrefs + (f'<div class="card-actions">{"".join(acts)}</div>\n' if acts else "") + note
            + licence_html(e.get("licence_note", "")) + '</div>\n</article>')


def render(ctx):
    lab = label(ctx, "bibliography")
    data = _load(ctx)
    cfg = ctx["config"].get("bibliography") or {}
    head = '<link rel="stylesheet" href="assets/content.css">'
    if not data["entries"]:
        return Page("bibliography", lab, lab, empty_state(lab), head_extra=head)
    jump, sections = [], []
    for g in cfg.get("groups", []):
        rows = data["groups"].get(g["id"], [])
        if not rows:
            continue
        jump.append(f'<li>{link("page", "#" + g["id"], g["label"] + " (" + str(len(rows)) + ")")}</li>')
        sections.append(
            f'<section class="card-group bib-group" id="{esc(g["id"])}" aria-labelledby="h-{esc(g["id"])}">\n'
            f'<h2 id="h-{esc(g["id"])}" class="group-title">{esc(g["label"])}</h2>\n<div class="bib-list">\n'
            + "\n".join(_entry_html(ctx, e) for e in rows) + "\n</div>\n</section>")
    body = '<ul class="bib-jump" aria-label="Jump to a group">' + "".join(jump) + "</ul>\n" + "\n".join(sections)
    return Page("bibliography", lab, lab, body, head_extra=head)
