"""Other writing: standalone essay pages and the links to them, all driven by site-config `other_writing`.

Each entry: slug, title, byline, date, source (a local JSON file read at build time only, never emitted),
source_key (dotted path to the text inside it), drop_header_lines (leading lines replaced by the entry's own
title/byline/date), link_label (e.g. "Essay: {title}"), scene (optional scene id that links to it), and
footnote/works-cited markers. The essay text is used verbatim; the only change is the replaced header block.
"""
import json
import re
from pathlib import Path

from render import Page
from render.common import empty_state, esc

HEAD = '<link rel="stylesheet" href="assets/paper.css">'
FOOTNOTE = re.compile(r"^\[(\d+)\]\s")
MARKER = re.compile(r"\[(\d+)\]")


def entries(config):
    """The configured other-writing entries (empty list when none)."""
    return config.get("other_writing") or []


def entry_for_scene(config, scene_id):
    """The entry linked from a scene viewer, or None."""
    for e in entries(config):
        if e.get("scene") == scene_id:
            return e
    return None


def link_text(entry):
    """The link label for an entry, with {title} filled in."""
    return entry.get("link_label", "{title}").replace("{title}", entry["title"])


def read_text(ctx, entry):
    """The essay text from the build-time source file, or '' when unreadable."""
    p = Path(entry["source"])
    if not p.is_absolute():
        p = ctx["root"] / p
    if not p.is_file():
        ctx["log"](f"other_writing: {entry['slug']} source not readable; page shows the empty state")
        return ""
    node = json.loads(p.read_text(encoding="utf-8-sig"))
    for key in entry["source_key"].split("."):
        node = node[key]
    return node.replace("\r\n", "\n")


def body_html(text, heading):
    """Paragraphs, footnotes and the Works Cited as HTML; the text itself is only escaped, never altered."""
    out, cited = [], False
    for block in (b for b in text.split("\n\n") if b.strip()):
        lines = block.split("\n")
        if len(lines) == 1 and lines[0] == heading:
            cited = True
            out.append(f'<h2 class="paper-h" id="works-cited">{esc(heading)}</h2>')
            continue
        if cited:
            out.append('<ul class="essay-cited">' + "".join(f"<li>{esc(l)}</li>" for l in lines) + "</ul>")
            continue
        for line in lines:
            m = FOOTNOTE.match(line)
            if m:
                n = m.group(1)
                out.append(f'<p class="essay-note" id="fn-{n}"><a href="#fnref-{n}">[{n}]</a> {esc(line[m.end():])}</p>')
            else:
                html = MARKER.sub(lambda k: f'<a class="essay-fn" id="fnref-{k.group(1)}" href="#fn-{k.group(1)}">[{k.group(1)}]</a>', esc(line))
                out.append(f"<p>{html}</p>")
    return "\n".join(out)


def render_entry(ctx, entry):
    """The Page for one other-writing entry."""
    raw = read_text(ctx, entry)
    lines = raw.split("\n")[entry.get("drop_header_lines", 0):]
    text = "\n".join(lines).lstrip("\n")
    if not text:
        return Page(entry["slug"], entry["title"], entry["title"], empty_state(entry["title"]), head_extra=HEAD)
    heading = entry.get("works_cited_heading", "Works Cited")
    meta = (f'<p class="essay-meta"><span class="essay-by">{esc(entry["byline"])}</span> '
            f'<time>{esc(entry["date"])}</time></p>')
    page = meta + f'\n<article class="paper essay" id="paper-text">\n{body_html(text, heading)}\n</article>'
    return Page(entry["slug"], entry["title"], entry["title"], page, head_extra=HEAD, in_nav=False)
