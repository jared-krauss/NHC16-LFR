"""Paper page: Jared's own plain-text paper, set as a long-form read with live figure references.

Source: config `paper_source` (default paper/paper.md), overridable with the NHC_PAPER_SOURCE environment variable.
Plain text with blank-line paragraphs, '#' / '##' / '###' headings, '> ' quotes, *italic* and **bold**. The first '#'
line is the page heading. "Fig. N", "Fig N", "Figure N" and "Figs. N-M" become links that open the figure viewer on
this page (media.html#fig-N without JavaScript); numbers absent from figures-config.json stay plain text and are
reported by the build. No paper text is generated here; the only wording is interface copy.
"""
import json
import os
import re
from pathlib import Path

from render import Page
from render.common import EMPTY_TEXT, esc, label

HEAD = '<link rel="stylesheet" href="assets/paper.css">\n<link rel="stylesheet" href="assets/viewer.css">'
SCRIPTS = '<script src="assets/viewer.js" defer></script>\n<script src="assets/paper.js" defer></script>'
EMPTY_LINE = "The paper text will appear here."
FIG_REF = re.compile(r"\b(Fig(?:ure)?s?\.?)(\s*)(\d+)(?:(\s*[-–]\s*)(\d+))?", re.I)
HEADING = re.compile(r"^(#{1,3})\s+(.*\S)\s*$")


def count(ctx):
    return 0


def has_body(ctx):
    """True when the paper file holds at least one block of text below the page heading."""
    p = source_path(ctx)
    if not p.is_file():
        return False
    blocks = parse(p.read_text(encoding="utf-8-sig"))
    if blocks and blocks[0][0] == "h" and blocks[0][1] == 1:
        blocks = blocks[1:]
    return bool(blocks)


def home_note(ctx):
    """The Home card line: the empty state while the paper has no text, else a neutral invitation."""
    return "Read along with the talk" if has_body(ctx) else EMPTY_TEXT


def source_path(ctx):
    """The paper file: NHC_PAPER_SOURCE, else config paper_source, else paper/paper.md."""
    env = os.environ.get("NHC_PAPER_SOURCE")
    if env:
        return Path(env) if os.path.isabs(env) else ctx["root"] / env
    return ctx["root"] / ctx["config"].get("paper_source", "paper/paper.md")


def parse(raw):
    """Split source text into blocks: ('h', level, text) | ('p', text) | ('q', text)."""
    blocks, buf, kind = [], [], None

    def flush():
        nonlocal buf, kind
        if buf:
            blocks.append((kind, " ".join(buf)))
        buf, kind = [], None

    for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        s = line.strip()
        if not s:
            flush()
            continue
        m = HEADING.match(s)
        if m:
            flush()
            blocks.append(("h", len(m.group(1)), m.group(2)))
            continue
        q = s.startswith(">")
        body = s[1:].strip() if q else s
        want = "q" if q else "p"
        if kind and kind != want:
            flush()
        kind = want
        buf.append(body)
    flush()
    return blocks


def slugify(text, used):
    """A unique anchor id from heading text."""
    base = re.sub(r"[^a-z0-9]+", "-", re.sub(r"<[^>]+>", "", text).lower()).strip("-") or "section"
    slug, n = base, 2
    while slug in used:
        slug, n = f"{base}-{n}", n + 1
    used.add(slug)
    return slug


def inline(text, figs, missing):
    """Escape text, apply *italic*/**bold*, and link figure references that exist in `figs`."""
    t = esc(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])", r"<em>\1</em>", t)

    def ref(n, shown):
        if n in figs:
            return f'<a class="fig-ref" data-link="page" href="media.html#fig-{n}" data-fig="{n}">{shown}</a>'
        missing.add(n)
        return shown

    def sub(m):
        word, gap, a, sep, b = m.group(1), m.group(2), int(m.group(3)), m.group(4), m.group(5)
        first = ref(a, f"{word}{gap}{m.group(3)}")
        if b is None:
            return first
        return first + sep + ref(int(b), b)

    return FIG_REF.sub(sub, t)


def render_body(blocks, figs, missing):
    """(html, headings) for the blocks after the page heading; headings are (level, id, text)."""
    used, heads, out = set(), [], []
    for b in blocks:
        if b[0] == "h":
            level = max(2, b[1])
            sid = slugify(b[2], used)
            heads.append((level, sid, re.sub(r"[*]+", "", b[2])))
            out.append(f'<h{level} id="{sid}" class="paper-h"><a href="#{sid}">{inline(b[2], figs, missing)}</a></h{level}>')
        elif b[0] == "q":
            out.append(f'<blockquote><p>{inline(b[1], figs, missing)}</p></blockquote>')
        else:
            out.append(f'<p>{inline(b[1], figs, missing)}</p>')
    return "\n".join(out), heads


def menu_html(figs, heads, egg=None):
    """The sticky menu button and its panel; hidden until paper.js enables it. `egg` is the paper_menu_egg config."""
    egg = egg or {}
    parts = ['<button type="button" class="paper-menu-btn" id="paper-menu-btn" aria-expanded="false" '
             'aria-controls="paper-menu" aria-label="Menu: figures and sections" hidden>'
             '<span class="paper-menu-icon" aria-hidden="true"><i></i><i></i><i></i></span>'
             '<span class="paper-menu-text">Menu</span></button>',
             '<div class="paper-menu" id="paper-menu" role="dialog" aria-label="Paper menu" hidden>',
             '<div class="paper-menu-head"><p class="paper-menu-title">Menu</p>'
             '<button type="button" class="paper-menu-close" aria-label="Close menu">Close</button></div>']
    if figs:
        items = "".join(f'<li><a data-link="page" href="media.html#fig-{f["n"]}" data-fig="{f["n"]}"><span class="pm-num">Fig. {f["n"]}</span>'
                        f'<span class="pm-name">{esc(f["title"])}</span></a></li>' for f in figs.values())
        parts.append(f'<h2 class="pm-h">Figures</h2><ul class="pm-list">{items}</ul>')
    if heads:
        items = "".join(f'<li class="pm-l{lv}"><a href="#{sid}" data-jump>{esc(t)}</a></li>' for lv, sid, t in heads)
        parts.append(f'<h2 class="pm-h">Sections</h2><ul class="pm-list">{items}</ul>')
    foot = '<li><a data-link="page" href="media.html">All figures</a></li>'
    if egg.get("label"):
        foot += f'<li><a class="pm-egg" href="{esc(egg.get("href", "scenes.html#stratford"))}">{esc(egg["label"])}</a></li>'
    parts.append(f'<ul class="pm-list pm-foot">{foot}</ul></div>')
    return "\n".join(parts)


def figure_data(figs):
    """JSON the viewer needs per figure, keyed by number."""
    return json.dumps({str(n): {"label": f"Fig. {n}: {f['title']}", "alt": f["alt"], "web": f["web"], "full": f["full"],
                                "w": f["web_w"], "h": f["web_h"]} for n, f in figs.items()}, ensure_ascii=False)


def other_writing_html(ctx):
    """The closing line linking each other-writing essay: label, linked title, date (all from config)."""
    from render.other_writing import entries
    lead = ctx["config"].get("paper_other_writing_label", "")
    rows = "".join(f'<p class="paper-other">{esc(lead)} <a href="{esc(e["slug"])}.html">{esc(e["title"])}</a>, {esc(e["date"])}</p>'
                   for e in entries(ctx["config"]))
    return rows + "\n" if rows else ""


def render(ctx):
    from render.media import figures
    lab = label(ctx, "paper")
    figs = {f["n"]: f for f in figures(ctx)}
    p = source_path(ctx)
    raw = ""
    if p.is_file():
        raw = p.read_text(encoding="utf-8-sig")
    else:
        ctx["log"](f"paper: {p.name} not found; page shows the empty line")
    blocks = parse(raw)
    h1 = lab
    if blocks and blocks[0][0] == "h" and blocks[0][1] == 1:
        h1, blocks = blocks[0][2], blocks[1:]
    missing = set()
    body, heads = render_body(blocks, figs, missing)
    for n in sorted(missing):
        print(f"WARNING paper: Fig. {n} is not in figures-config.json; left as plain text", flush=True)
    if not body:
        body = f'<p class="paper-empty">{EMPTY_LINE}</p>'
    page = (f'<article class="paper" id="paper-text">\n{body}\n</article>\n' + other_writing_html(ctx) + menu_html(figs, heads, ctx["config"].get("paper_menu_egg"))
            + f'\n<script type="application/json" id="paper-figures">{figure_data(figs).replace("</", "<\\/")}</script>')
    return Page("paper", lab, re.sub(r"\*+", "", h1), page, head_extra=HEAD, scripts_extra=SCRIPTS)
