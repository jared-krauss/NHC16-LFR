"""Build the audience site into docs/.

    python build.py [--selections PATH] [--config-overlay PATH] [--out docs]

Never crashes on missing, empty or half-filled selections; prints one line per skipped item and why.
Exit 0 on success.
"""
import argparse
import copy
import json
import math
import re
import shutil
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from render import Page, load  # noqa: E402
from render.common import empty_state, esc, make_copy_asset, label  # noqa: E402

LIST_KEYS = ["whole_files", "posters_a3", "charts_ready", "charts_tweak", "news", "photos", "splats"]
REQUIRED = {"whole_files": ("title",), "posters_a3": ("title",), "charts_ready": ("id",), "charts_tweak": ("id",),
            "news": ("title",), "photos": (), "splats": ()}
LEAK_PATTERNS = [rb"(?i)user1", rb"(?i)\.ts\.net", rb"(?i)tailscale", rb"(?i)localhost", rb"127\.0\.0\.1",
                 rb":878[78]\b", rb"\b[CDE]:[\\/]", rb"(?<![A-Za-z])file:"]


def log(msg):
    print("skip: " + msg, flush=True)


def item_validators():
    """Per-list item validators built from schema/selections.schema.json (empty dict if jsonschema is unavailable)."""
    try:
        import jsonschema
        schema = read_json(ROOT / "schema" / "selections.schema.json")
        props = schema.get("properties", {})
        return {k: jsonschema.Draft202012Validator(props[k]["items"]) for k in LIST_KEYS
                if isinstance(props.get(k), dict) and isinstance(props[k].get("items"), dict)}
    except Exception as e:
        print(f"selections: schema validation unavailable ({type(e).__name__}: {e})", flush=True)
        return {}


def schema_reason(validator, item):
    """First schema complaint about an item as a short phrase, or ''."""
    errs = sorted(validator.iter_errors(item), key=lambda e: list(map(str, e.absolute_path)))
    if not errs:
        return ""
    e = errs[0]
    where = ".".join(str(x) for x in e.absolute_path)
    return f"{where}: {e.message[:80]}" if where else e.message[:80]


def deep_merge(a, b):
    """Dicts merge recursively; everything else (including lists) is replaced."""
    out = copy.deepcopy(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def load_selections(path):
    """Read and normalise selections: every list key present, only dict items with their required field."""
    raw = {}
    if path:
        p = Path(path)
        try:
            data = read_json(p) if p.is_file() else None
            if data is None:
                print(f"selections: {p.name} not found, treated as empty", flush=True)
            elif isinstance(data, dict):
                raw = data
            else:
                print(f"selections: {p.name} is not an object, treated as empty", flush=True)
        except (OSError, ValueError) as e:
            print(f"selections: {p.name} unreadable ({type(e).__name__}), treated as empty", flush=True)
    sel = {k: v for k, v in raw.items() if k not in LIST_KEYS}
    validators = item_validators()
    for key in LIST_KEYS:
        items = raw.get(key)
        if not isinstance(items, list):
            if items not in (None, [], {}):
                log(f"{key}: not a list, ignored")
            items = []
        kept = []
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                print(f"invalid {key}[{i}]: not an object -> skipped", flush=True)
                continue
            reason = schema_reason(validators[key], it) if key in validators else ""
            if reason:
                print(f"invalid {key}[{i}]: {reason} -> skipped", flush=True)
                continue
            missing = [f for f in REQUIRED[key] if not (isinstance(it.get(f), str) and it[f].strip())]
            if missing:
                print(f"invalid {key}[{i}]: no {missing[0]} -> skipped", flush=True)
                continue
            if key == "whole_files" and it.get("use") not in ("print", "host", "link"):
                print(f"invalid {key}[{i}]: use is '{it.get('use')}', need print|host|link -> skipped", flush=True)
                continue
            kept.append(it)
        sel[key] = kept
    return sel


def render_qr(url, out):
    """Write qr.svg and qr.png (error correction M, quiet zone 4 modules, dark on light). Returns display size."""
    import segno
    qr = segno.make(url, error="m", micro=False)
    modules = qr.symbol_size(border=4)[0]
    qr.save(out / "qr.svg", kind="svg", scale=4, border=4, dark="#000000", light="#ffffff", xmldecl=False)
    qr.save(out / "qr.png", kind="png", scale=math.ceil(1000 / modules) + 1, border=4, dark="#000000", light="#ffffff")
    return {"px": modules * 4}


def copy_tree(src, dst, skip_ext=(".mjs",)):
    if not src.is_dir():
        return
    for f in src.rglob("*"):
        if f.is_file():
            if f.suffix.lower() in skip_ext:
                log(f"{f.relative_to(ROOT).as_posix()}: .mjs not published")
                continue
            t = dst / f.relative_to(src)
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, t)


def _unlock_and_retry(func, path, exc):
    """rmtree error handler: clear a read-only flag copied from a source file and retry once."""
    import os
    import stat
    os.chmod(path, stat.S_IWRITE)
    func(path)


def wipe(out):
    """Remove the output folder's contents, refusing to touch the project root or its parents."""
    out = out.resolve()
    if out == ROOT or out in ROOT.parents or len(out.parts) < 3:
        raise SystemExit(f"refusing to wipe {out}")
    if out.exists():
        shutil.rmtree(out, onexc=_unlock_and_retry)
    out.mkdir(parents=True)


def nav_html(config, current):
    rows = []
    for s in config["sections"]:
        cur = ' aria-current="page"' if s["slug"] == current else ""
        rows.append(f'<li><a href="{esc(s["slug"])}.html"{cur}>{esc(s["label"])}</a></li>')
    return "\n".join(rows)


def footer_html(config):
    return "\n".join(f'<li><a href="{esc(s["slug"])}.html">{esc(s["label"])}</a></li>' for s in config["sections"])


def short_name(config):
    site = config["site"]
    if site.get("short_name"):
        return site["short_name"]
    seg = [p for p in site.get("public_url", "").split("/") if p]
    return seg[-1] if len(seg) > 1 else "Home"


def wrap(page, config, template):
    site = config["site"]
    hidden = {h["slug"]: h["label"] for h in config.get("hidden_pages", [])}
    head = page.head_extra
    if page.noindex:
        head = '<meta name="robots" content="noindex">\n' + head
    title = page.title if page.slug == "index" else f"{page.title} | {short_name(config)}"
    egg = hidden.get("scenes", "3D scenes")
    subs = {"lang": esc(site.get("lang", "en")), "title": esc(title), "head_extra": head,
            "site_name": esc(short_name(config)), "nav": nav_html(config, page.slug), "h1": esc(page.h1),
            "body": page.body_html, "footer_links": footer_html(config), "egg_label": esc(egg),
            "scripts_extra": page.scripts_extra}
    return re.sub(r"\{\{(\w+)\}\}", lambda m: subs.get(m.group(1), ""), template)


def write_redirects(config, out):
    """Write a small meta-refresh page at each retired page URL (config redirects: from slug -> to url)."""
    for r in config.get("redirects", []):
        to = r["to"]
        html = ('<!doctype html>\n<html lang="%s">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
                '<meta name="robots" content="noindex">\n<title>Moved | %s</title>\n'
                '<meta http-equiv="refresh" content="0; url=%s">\n<link rel="canonical" href="%s">\n</head>\n<body>\n'
                '<p>This page has moved. <a href="%s">Continue to the new page</a>.</p>\n</body>\n</html>\n'
                % (esc(config["site"].get("lang", "en")), esc(short_name(config)), esc(to), esc(to), esc(to)))
        (out / f"{r['from']}.html").write_text(html, encoding="utf-8", newline="\n")


def scan_leaks(out):
    """Return the number of output files holding local-path or internal-host text."""
    hits = 0
    for f in out.rglob("*"):
        if f.suffix.lower() in (".html", ".css", ".js", ".svg", ".json") and "vendor" not in f.relative_to(out).parts:
            data = f.read_bytes()
            for pat in LEAK_PATTERNS:
                if re.search(pat, data):
                    hits += 1
                    print(f"LEAK local/internal text in {f.relative_to(out).as_posix()} ({pat.decode()})", flush=True)
                    break
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selections")
    ap.add_argument("--config-overlay")
    ap.add_argument("--out", default="docs")
    a = ap.parse_args()

    config = read_json(ROOT / "site-config.json")
    if a.config_overlay:
        config = deep_merge(config, read_json(a.config_overlay))
    out = Path(a.out)
    out = out if out.is_absolute() else Path.cwd() / out

    sel = load_selections(a.selections if a.selections else config.get("selections_path"))
    wipe(out)
    (out / ".nojekyll").write_text("", encoding="utf-8")
    copy_tree(ROOT / "assets", out / "assets")
    copy_tree(ROOT / "vendor", out / "vendor")

    ctx = {"config": config, "sel": sel, "out": out, "copy_asset": make_copy_asset(out, log), "log": log, "root": ROOT}
    try:
        ctx["qr"] = render_qr(config["site"]["public_url"], out)
    except Exception as e:
        print(f"WARNING qr not written: {type(e).__name__}: {e}", flush=True)

    template = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    slugs = [s["slug"] for s in config["sections"]] + [h["slug"] for h in config.get("hidden_pages", [])]
    for slug in slugs:
        try:
            mod = load(slug)
            if mod is None:
                raise RuntimeError("no render module")
            page = mod.render(ctx)
        except Exception as e:
            traceback.print_exc()
            print(f"skip: page {slug} failed ({type(e).__name__}: {e}); wrote an empty page", flush=True)
            lab = label(ctx, slug)
            page = Page(slug, lab, lab, empty_state(lab))
        (out / f"{slug}.html").write_text(wrap(page, config, template), encoding="utf-8", newline="\n")

    write_redirects(config, out)
    for f in list(out.rglob("*.mjs")):
        f.unlink()
        log(f"{f.name}: .mjs removed from output")
    leaks = scan_leaks(out)
    print(f"built {len(slugs)} pages into {out.name}", flush=True)
    if leaks:
        print(f"BUILD FAILED: {leaks} output file(s) leak local paths or internal hosts", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
