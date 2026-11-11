"""Acceptance checks for the NHC16-LFR audience site (SPEC.md bar B1-B26). BUILDERS MAY NOT EDIT.

Run:  D:\\Dev\\tools\\.venv\\Scripts\\python.exe checks\\run_checks.py [--fixture empty|half|full|missing|real|all]
                                                                  [--only B1,B3] [--skip-build] [--root PATH]
Markup contract: checks/CONTRACT.md.  Reports: checks/_out/report.json and report.md.
"""
import argparse
import copy
import functools
import hashlib
import json
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
from contextlib import contextmanager
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

HERE = Path(__file__).resolve().parent
AXE = HERE / "vendor" / "axe.min.js"
FIXTURES = ["empty", "half", "full", "missing"]
ALL_FIXTURES = FIXTURES + ["real"]
MOBILE = (375, 812)
NARROW = (320, 640)
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE_RE = re.compile(r"^((\d{1,2} )?(%s) )?\d{4}$" % MONTHS)
SIZE_RE = re.compile(r"\d+(\.\d+)?\s*(KB|MB|kB|KiB|MiB)")
VENDOR_RE = re.compile(r"(^|/)(vendor|libs)/|\.min\.js$|plotly|playcanvas", re.I)

JS_CARDS = r"""() => [...document.querySelectorAll('article.card')].map(c => {
  const q = s => c.querySelector(s);
  const t = q('.card-title'), sm = q('.card-meta .source'), so = sm || q('.fig-source'), d = q('.card-meta .date'), k = q('.card-kind');
  const pos = (a, b) => a && b ? !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) : false;
  const es = getComputedStyle(c);
  const emptyText = [...c.querySelectorAll('*')].some(e => e.children.length === 0 && e.textContent.trim() === 'On its way');
  return {kind: c.dataset.kind || '', empty: c.classList.contains('card--empty'), title: t ? t.textContent.trim() : '',
    source: so ? so.textContent.trim() : '', date: d ? d.textContent.trim() : '', badge: k ? k.textContent.trim() : '',
    order: [t, sm, d, k].filter(Boolean).every((x, i, a) => i === 0 || pos(a[i - 1], x)), emptyText: emptyText, borderStyle: es.borderTopStyle,
    color: es.color, borderColor: es.borderTopColor, imgs: c.querySelectorAll('img').length,
    imgAlts: [...c.querySelectorAll('img')].map(i => i.getAttribute('alt') || ''),
    links: [...c.querySelectorAll('a[href]')].map(a => ({href: a.getAttribute('href'), kind: a.dataset.link || '', text: (a.innerText || '').trim()})),
    spinner: !!c.querySelector('progress,[role=progressbar],.spinner,.loader'),
    text: c.textContent.replace(/\s+/g, ' ').trim()};
})"""

JS_ANCHORS = r"""() => [...document.querySelectorAll('a[href]')].map(a => ({
  href: a.getAttribute('href'), text: (a.innerText || '').trim(), aria: a.getAttribute('aria-label') || '',
  rel: a.getAttribute('rel') || '', kind: a.dataset.link || '', inMain: !!a.closest('main'),
  skip: a.classList.contains('skip-link'), egg: a.classList.contains('egg'),
  imgAlt: [...a.querySelectorAll('img')].map(i => i.alt).join(' '),
  before: getComputedStyle(a, '::before').content, after: getComputedStyle(a, '::after').content,
  svg: a.querySelectorAll('svg,img').length, deco: getComputedStyle(a).textDecorationLine,
  bstyle: getComputedStyle(a).borderBottomStyle}))"""

JS_TEXT_SIZES = r"""() => {
  const res = []; const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let n;
  while (n = w.nextNode()) {
    const t = n.nodeValue.trim(); if (!t) continue; const e = n.parentElement;
    if (e.closest('script,style,noscript,.skip-link')) continue;
    const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden') continue;
    const r = e.getBoundingClientRect(); if (r.width <= 1 || r.height <= 1) continue;
    res.push({size: parseFloat(s.fontSize), fam: s.fontFamily, wt: s.fontWeight, tag: e.tagName, txt: t.slice(0, 24),
      meta: !!e.closest('.card-meta,.card-kind,small,footer,.slide-counter,figcaption')});
  } return res; }"""

JS_BODY_LH = r"""() => { const o = []; for (const e of document.querySelectorAll('main p, main li, main dd, main blockquote')) {
  const s = getComputedStyle(e); if (e.closest('.card-meta,nav,.paper')) continue;
  const lh = s.lineHeight, fs = parseFloat(s.fontSize);
  o.push({lh: lh, ratio: lh === 'normal' ? 1.2 : parseFloat(lh) / fs, tag: e.tagName}); } return o; }"""

JS_TARGETS = r"""() => { const o = []; for (const e of document.querySelectorAll('a[href],button,[role=button],input,select,textarea,summary')) {
  const r = e.getBoundingClientRect(), s = getComputedStyle(e);
  if (r.width === 0 || r.height === 0 || s.visibility === 'hidden' || s.display === 'none') continue;
  if (e.matches('a.skip-link') || (r.right < 0) || (r.bottom < 0 && r.top < -5000)) continue;
  const inline = e.tagName === 'A' && !!e.closest('main p') && !e.closest('.card');
  const strict = !!(e.closest('nav') || e.matches('[data-action]') || e.closest('.card') || e.matches('a.egg'));
  o.push({d: e.tagName.toLowerCase() + (e.className ? '.' + String(e.className).split(' ')[0] : '') + ' "' + (e.textContent || '').trim().slice(0, 20) + '"',
    w: Math.round(r.width), h: Math.round(r.height), inline: inline, strict: strict}); } return o; }"""

JS_FOCUS = r"""() => { const e = document.activeElement; if (!e || e === document.body) return null;
  if (e.__seen) return {dup: true}; e.__seen = true;
  const s = getComputedStyle(e), r = e.getBoundingClientRect();
  const top = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
  return {tag: e.tagName.toLowerCase(), text: (e.textContent || e.getAttribute('aria-label') || '').trim().slice(0, 24),
    ow: parseFloat(s.outlineWidth), os: s.outlineStyle, bs: s.boxShadow, covered: !!top && !(e === top || e.contains(top) || top.contains(e)),
    inview: r.bottom > 0 && r.top < innerHeight, insideSlideshow: !!e.closest('#slideshow'), action: e.dataset.action || ''}; }"""

JS_AXE = r"""() => axe.run().then(r => ({v: r.violations.map(v => ({id: v.id, impact: v.impact, n: v.nodes.length,
  sel: v.nodes.slice(0, 2).map(n => n.target.join(' '))}))}))"""


def deep_merge(a, b):
    out = copy.deepcopy(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []
        self.inline_js = []
        self.styles = []
        self._tag = None

    def handle_starttag(self, tag, attrs):
        self._tag = tag
        a = dict(attrs)
        for key in ("href", "src", "poster", "data-src"):
            if a.get(key) is not None:
                self.refs.append((tag, key, a[key]))
        for key in ("srcset", "data-srcset"):
            if a.get(key):
                for part in a[key].split(","):
                    if part.strip():
                        self.refs.append((tag, key, part.strip().split()[0]))
        if a.get("style"):
            self.styles.append(a["style"])

    def handle_data(self, data):
        if self._tag == "script":
            self.inline_js.append(data)
        elif self._tag == "style":
            self.styles.append(data)

    def handle_endtag(self, tag):
        self._tag = None


def parse_html(path):
    p = LinkParser()
    p.feed(Path(path).read_text(encoding="utf-8", errors="replace"))
    return p


def slug_of(href, page_url):
    full = urlparse(urljoin(page_url, href))
    name = full.path.rsplit("/", 1)[-1]
    if name in ("", "index.html"):
        return "index"
    return name[:-5] if name.endswith(".html") else name


class Ctx:
    def __init__(self, fx, out, cfg, sel, browser, base, only, results):
        self.fx, self.out, self.cfg, self.sel = fx, out, cfg, sel
        self.browser, self.base, self.only, self.results = browser, base, only, results
        self.nav = [s["slug"] for s in cfg["sections"]]
        self.labels = {s["slug"]: s["label"] for s in cfg["sections"] + cfg.get("hidden_pages", [])}
        self.hidden = [s["slug"] for s in cfg.get("hidden_pages", [])]
        self.prose = [s["slug"] for s in cfg["sections"] if s.get("prose")]
        self.all_slugs = self.nav + self.hidden
        self._axe = {}

    def rec(self, cid, status, ev):
        if self.only and cid.split("-")[0] not in self.only:
            return
        self.results.append({"id": cid, "fixture": self.fx, "status": status, "evidence": ev})

    def exists(self, slug):
        return (self.out / f"{slug}.html").is_file()

    def present(self, slugs=None):
        return [s for s in (slugs or self.all_slugs) if self.exists(s)]

    def url(self, slug):
        return f"{self.base}/{slug}.html"

    @contextmanager
    def page(self, slug, size=MOBILE, js=True, reduced=False, query="", wait="load", path=None, touch=False):
        ctx = self.browser.new_context(viewport={"width": size[0], "height": size[1]}, java_script_enabled=js,
                                       reduced_motion="reduce" if reduced else "no-preference", has_touch=touch)
        pg = ctx.new_page()
        pg.set_default_timeout(15000)
        reqs, resps = [], []
        pg.on("request", lambda r: reqs.append(r.url))
        pg.on("response", lambda r: resps.append(r))
        try:
            pg.goto((self.base + "/" + path if path else self.url(slug)) + query, wait_until=wait)
            yield pg, reqs, resps
        finally:
            ctx.close()

    def axe(self, slug):
        if slug not in self._axe:
            with self.page(slug) as (pg, _, _):
                pg.add_script_tag(path=str(AXE))
                self._axe[slug] = pg.evaluate(JS_AXE)["v"]
        return self._axe[slug]

    def files(self):
        return [p for p in self.out.rglob("*") if p.is_file()]

    def rel(self, p):
        return p.relative_to(self.out).as_posix()

    def dwell_wait(self):
        d = self.cfg.get("slideshow", {}).get("dwell_seconds", {})
        return max(d.get("image", 7), d.get("chart", 8)) + 2


def short(items, n=4):
    items = list(items)
    s = "; ".join(str(i) for i in items[:n])
    return s + (f" (+{len(items) - n} more)" if len(items) > n else "")


def verdict(c, cid, fails, ok_msg):
    c.rec(cid, "FAIL" if fails else "PASS", short(fails) if fails else ok_msg)


def origin(c):
    """The first section after Home: the page the slideshow-exit and Back tests start from."""
    return next((x for x in c.nav if x != "index"), "index")


def counter(pg):
    t = pg.locator("#slideshow .slide-counter").first.inner_text().strip()
    m = re.match(r"^(\d+)\s*/\s*(\d+)$", t)
    return (int(m.group(1)), int(m.group(2))) if m else None


# ---------------------------------------------------------------- B1 - B3

def b1(c):
    fails = []
    for slug in c.present():
        for size in (MOBILE, NARROW):
            with c.page(slug, size) as (pg, _, _):
                r = pg.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
                if r[0] > r[1]:
                    fails.append(f"{slug}@{size[0]}: scrollWidth {r[0]} > {r[1]}")
                if size == MOBILE:
                    meta = pg.evaluate("() => (document.querySelector('meta[name=viewport]') || {}).content || ''")
                    if not meta:
                        fails.append(f"{slug}: no viewport meta")
                    elif re.search(r"user-scalable\s*=\s*(no|0)|maximum-scale", meta, re.I):
                        fails.append(f"{slug}: viewport blocks zoom ({meta})")
    verdict(c, "B1", fails or (["no pages built"] if not c.present() else []),
            f"no horizontal overflow at 375 and 320 on {len(c.present())} pages; zoom not blocked")


def static_links(c, slug):
    p = parse_html(c.out / f"{slug}.html")
    return {slug_of(r[2], c.url(slug)) for r in p.refs if r[1] == "href" and r[0] == "a"
            and not urlparse(r[2]).scheme and not r[2].startswith("#") and not re.search(r"\.(pdf|png|jpe?g|webp|sog|svg|js|css|json)$", urlparse(r[2]).path)}


def b2(c):
    fails = []
    missing = [s for s in c.all_slugs if not c.exists(s)]
    if missing:
        fails.append("pages not built: " + ",".join(missing))
    if c.exists("index"):
        with c.page("index") as (pg, _, _):
            navs = pg.evaluate("""() => [...document.querySelectorAll('nav a[href]')].map(a => {const r = a.getBoundingClientRect(), s = getComputedStyle(a);
              return {href: a.getAttribute('href'), x: r.x, y: r.y, w: r.width, h: r.height, vis: s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0};})""")
            toggle = pg.evaluate("() => !!document.querySelector('header [aria-expanded], nav [aria-expanded], .menu-toggle, .hamburger, nav button, header button[aria-controls]')")
            if toggle:
                fails.append("menu toggle/hamburger present")
            seen = {slug_of(n["href"], c.url("index")): n for n in navs}
            for s in c.nav:
                n = seen.get(s)
                if not n or not n["vis"]:
                    fails.append(f"nav link to {s} missing/not visible on load")
                elif n["x"] < 0 or n["x"] + n["w"] > MOBILE[0] + 1 or n["y"] >= MOBILE[1]:
                    fails.append(f"nav link {s} outside the 375x812 viewport")
    if c.exists("slideshow"):
        with c.page("slideshow") as (pg, _, _):
            home = pg.evaluate(r"""() => [...document.querySelectorAll('a[data-link=page]')].filter(a => !a.closest('nav') && /^(\.\/)?(index\.html)?$/.test(a.getAttribute('href').split('#')[0]) ).map(a => {
              const r = a.getBoundingClientRect(), s = getComputedStyle(a); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth; })""")
            if not any(home):
                fails.append("slideshow page has no visible Home link (a[data-link=page] to index outside the nav)")
    for s in c.present(c.nav):
        links = static_links(c, s)
        need = set(c.nav) - {s}
        if need - links:
            fails.append(f"{s} lacks links to {','.join(sorted(need - links))}")
    depth = {"index": 0}
    frontier = ["index"]
    for d in (1, 2):
        nxt = []
        for s in frontier:
            if c.exists(s):
                for t in static_links(c, s):
                    if t not in depth and c.exists(t):
                        depth[t] = d
                        nxt.append(t)
        frontier = nxt
    for s in c.all_slugs:
        if c.exists(s) and s not in depth:
            fails.append(f"{s} not reachable from index in <=2 taps")
    verdict(c, "B2", fails, "all section links visible on load, no menu toggle, full cross-links, every page <=2 taps from index")


def b3(c):
    fails = []
    for f in c.files():
        r = c.rel(f)
        if f.suffix in (".js", ".html") and not VENDOR_RE.search(r):
            txt = f.read_text(encoding="utf-8", errors="replace")
            if re.search(r"pushState", txt):
                fails.append(f"pushState in {r}")
            if re.search(r"(before)?unload", txt):
                fails.append(f"unload/beforeunload in {r}")
    hops = [s for s in c.nav if s != "index" and c.exists(s)][:3]
    if c.exists("index") and len(hops) == 3:
        with c.page("index") as (pg, _, _):
            chain = [pg.url]
            for s in hops:
                pg.click(f'nav a[href$="{s}.html"]')
                pg.wait_for_load_state("load")
                chain.append(pg.url)
            back = []
            for _ in range(3):
                pg.go_back()
                back.append(pg.url)
            if back != [chain[2], chain[1], chain[0]]:
                fails.append(f"Back order wrong: {back} vs {chain[::-1][1:]}")
    elif c.exists("index"):
        fails.append("cannot run hop test: fewer than 3 section pages built")
    if c.exists(origin(c)) and c.exists("slideshow"):
        with c.page(origin(c)) as (pg, _, _):
            start = pg.url
            pg.click('nav a[href$="slideshow.html"]')
            pg.wait_for_load_state("load")
            nxt = pg.locator('#slideshow [data-action=next]')
            for _ in range(3):
                if nxt.count():
                    nxt.first.click()
            pg.go_back()
            if pg.url != start:
                fails.append(f"after slideshow Next x3, one Back landed on {pg.url}, expected {start}")
    verdict(c, "B3", fails, "no pushState/unload in own JS; 3 hops + 3 Back in order; one Back leaves slideshow")


# ---------------------------------------------------------------- B4 - B10

def b4(c):
    fails = []
    for s in c.present():
        with c.page(s) as (pg, _, _):
            r = pg.evaluate("""() => { const all = [...document.querySelectorAll('nav a')], cur = all.filter(a => a.getAttribute('aria-current') === 'page');
              const sig = a => { const s = getComputedStyle(a); return [s.fontWeight, s.textDecorationLine, s.borderBottomWidth + s.borderBottomStyle,
                s.borderLeftWidth + s.borderLeftStyle, getComputedStyle(a, '::before').content, getComputedStyle(a, '::after').content, s.fontStyle].join('|'); };
              const others = all.filter(a => !cur.includes(a)).map(sig);
              const h1 = document.querySelector('h1');
              return {n: cur.length, href: cur[0] ? cur[0].getAttribute('href') : '', cue: cur[0] ? !others.includes(sig(cur[0])) : false,
                h1: h1 ? h1.textContent.trim() : ''}; }""")
            if s in c.nav:
                if r["n"] != 1:
                    fails.append(f"{s}: {r['n']} aria-current links")
                elif slug_of(r["href"], c.url(s)) != s:
                    fails.append(f"{s}: aria-current points at {r['href']}")
                elif not r["cue"]:
                    fails.append(f"{s}: current link has no non-colour cue")
            elif r["n"]:
                fails.append(f"{s}: hidden page has aria-current in nav")
            if not r["h1"]:
                fails.append(f"{s}: no h1")
            elif s != "index" and r["h1"].lower() != c.labels[s].lower():
                fails.append(f"{s}: h1 '{r['h1']}' != label '{c.labels[s]}'")
    verdict(c, "B4", fails, "aria-current + non-colour cue on current link; h1 matches label (index h1 only needs to exist)")


def b5(c):
    fails = []
    for s in c.present():
        with c.page(s) as (pg, _, _):
            pg.keyboard.press("Tab")
            r = pg.evaluate("""() => { const e = document.activeElement, r = e.getBoundingClientRect(), s = getComputedStyle(e), m = document.querySelector('main#main');
              return {tag: e.tagName, href: e.getAttribute('href'), w: r.width, h: r.height, l: r.left, t: r.top, op: parseFloat(s.opacity), main: !!m, vw: innerWidth}; }""")
            if not r["main"]:
                fails.append(f"{s}: no main#main")
            if r["tag"] != "A" or r["href"] != "#main":
                fails.append(f"{s}: first Tab lands on {r['tag']} {r['href']}, not skip link to #main")
            elif r["w"] < 20 or r["h"] < 12 or r["op"] == 0 or r["l"] < -1 or r["t"] < -1 or r["l"] + r["w"] > r["vw"] + 1:
                fails.append(f"{s}: skip link not visible on focus ({r})")
    verdict(c, "B5", fails, "skip link first, visible on focus, targets main#main")


def b6(c):
    fails = []
    for s in c.present():
        with c.page(s) as (pg, _, _):
            r = pg.evaluate("""() => ({hs: [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map(h => +h.tagName[1]), h1: document.querySelectorAll('h1').length,
              header: !!document.querySelector('header'), nav: !!document.querySelector('nav[aria-label]'), main: !!document.querySelector('main'), footer: !!document.querySelector('footer')})""")
            if r["h1"] != 1:
                fails.append(f"{s}: {r['h1']} h1")
            prev = 0
            for lv in r["hs"]:
                if lv > prev + 1:
                    fails.append(f"{s}: heading jumps h{prev}->h{lv}")
                    break
                prev = lv
            for k in ("header", "nav", "main", "footer"):
                if not r[k]:
                    fails.append(f"{s}: missing landmark {k}")
        bad = [v for v in c.axe(s) if v["impact"] in ("serious", "critical") and v["id"] != "color-contrast"]
        for v in bad:
            fails.append(f"{s}: axe {v['id']} ({v['impact']}) {v['sel'][:1]}")
    verdict(c, "B6", fails, "one h1, no skipped levels, landmarks, axe zero serious/critical (contrast reported under B10)")


def b7(c):
    fails = []
    for s in c.present():
        with c.page(s) as (pg, _, _):
            n = 0
            for _ in range(90):
                pg.keyboard.press("Tab")
                r = pg.evaluate(JS_FOCUS)
                if r is None or r.get("dup"):
                    break
                n += 1
                if (r["os"] == "none" or r["ow"] == 0) and r["bs"] == "none":
                    fails.append(f"{s}: no focus indicator on {r['tag']} '{r['text']}'")
                if r["inview"] and r["covered"]:
                    fails.append(f"{s}: focused {r['tag']} '{r['text']}' covered by another element")
            if n == 0:
                fails.append(f"{s}: nothing focusable")
    for f in c.files():
        if f.suffix == ".css" and not VENDOR_RE.search(c.rel(f)):
            txt = f.read_text(encoding="utf-8", errors="replace")
            if re.search(r"outline\s*:\s*(none|0)\s*[;}]", txt) and not re.search(r":focus(-visible)?[^{]*\{[^}]*(outline|box-shadow)", txt):
                fails.append(f"{c.rel(f)}: outline removed with no focus replacement")
    verdict(c, "B7", fails, "every focusable shows an outline/ring and is not covered by a sticky element")


def b8(c):
    fails = []
    for s in c.present():
        with c.page(s) as (pg, _, _):
            for t in pg.evaluate(JS_TARGETS):
                if t["strict"] and (t["w"] < 44 or t["h"] < 44):
                    fails.append(f"{s}: {t['d']} {t['w']}x{t['h']} <44")
                elif not t["inline"] and (t["w"] < 24 or t["h"] < 24):
                    fails.append(f"{s}: {t['d']} {t['w']}x{t['h']} <24")
    verdict(c, "B8", fails, "nav/controls/card links >=44x44, nothing interactive <24x24 (inline text links exempt)")


def b9(c):
    fails = []
    bad_text = re.compile(r"^(click here|read more|here|more|link)$", re.I)
    for s in c.present():
        with c.page(s) as (pg, _, _):
            for a in pg.evaluate(JS_ANCHORS):
                if a["skip"]:
                    continue
                name = " ".join(x for x in (a["text"], a["aria"], a["imgAlt"]) if x).strip()
                label = a["aria"] or a["text"] or a["imgAlt"]
                if not name:
                    fails.append(f"{s}: link {a['href']} has no accessible name")
                    continue
                if bad_text.match(label.strip()):
                    fails.append(f"{s}: vague link text '{label}'")
                href = a["href"]
                absolute = bool(urlparse(href).netloc)
                if href.lower().split("?")[0].endswith(".pdf") or (a["kind"] == "file" and "pdf" in href.lower()):
                    if "PDF" not in name or not SIZE_RE.search(name):
                        fails.append(f"{s}: PDF link '{name[:40]}' lacks 'PDF' + size")
                if absolute and urlparse(href).netloc != urlparse(c.base).netloc:
                    if a["kind"] != "external":
                        fails.append(f"{s}: external link {href[:40]} not marked data-link=external")
                    if "noopener" not in a["rel"]:
                        fails.append(f"{s}: external link {href[:40]} lacks rel=noopener")
                    if not re.search(r"opens|external", name, re.I):
                        fails.append(f"{s}: external link '{name[:30]}' does not say it opens elsewhere")
    verdict(c, "B9", fails, "link texts make sense alone; PDF links state PDF+size; external links noopener + 'opens'")


def b10(c):
    fails = []
    for s in c.present():
        for v in c.axe(s):
            if v["id"] == "color-contrast":
                fails.append(f"{s}: contrast {v['n']} nodes {v['sel'][:2]}")
    verdict(c, "B10", fails, "axe color-contrast clean on every page (incl. empty-state text); large-text/UI 3:1 partly covered by axe")


# ---------------------------------------------------------------- B11 - B16

def b11(c):
    fails = []
    for s in c.present():
        with c.page(s) as (pg, _, _):
            items = pg.evaluate(JS_TEXT_SIZES)
            sizes = {round(i["size"], 1) for i in items}
            fams = {i["fam"] for i in items}
            wts = {i["wt"] for i in items}
            if len(sizes) > 4:
                fails.append(f"{s}: {len(sizes)} font sizes {sorted(sizes)}")
            if len(fams) > 1:
                fails.append(f"{s}: {len(fams)} font families")
            if len(wts) > 2:
                fails.append(f"{s}: {len(wts)} weights {sorted(wts)}")
            for i in items:
                if i["size"] < 13 or (i["size"] < 16 and not i["meta"]):
                    fails.append(f"{s}: {i['size']}px {i['tag']} '{i['txt']}'")
                    break
            lh = pg.evaluate(JS_BODY_LH)
            for r in lh:
                if not 1.4 <= r["ratio"] <= 1.6:
                    fails.append(f"{s}: line-height {r['lh']} ratio {r['ratio']:.2f} on {r['tag']}")
                    break
            if not lh:
                r = pg.evaluate("() => { const s = getComputedStyle(document.body); return s.lineHeight === 'normal' ? 1.2 : parseFloat(s.lineHeight) / parseFloat(s.fontSize); }")
                if not 1.4 <= r <= 1.6:
                    fails.append(f"{s}: body line-height ratio {r:.2f}")
    verdict(c, "B11", fails, "body>=16px, meta>=13px, <=4 sizes, 1 family, <=2 weights, line-height 1.4-1.6")


def b12(c):
    fails = []
    for s in c.present([x for x in c.all_slugs if x not in c.prose]):
        with c.page(s) as (pg, _, _):
            for k in pg.evaluate(JS_CARDS):
                tag = f"{s}/{k['title'][:24] or '?'}"
                if k["kind"] not in ("chart", "poster", "pdf", "link", "news", "section", "empty", "figure"):
                    fails.append(f"{tag}: bad data-kind '{k['kind']}'")
                if not k["title"]:
                    fails.append(f"{tag}: empty title")
                if k["empty"] or k["kind"] in ("empty", "section"):
                    continue
                if not k["source"] and k["kind"] not in ("pdf", "link"):
                    fails.append(f"{tag}: no source")
                if k["date"] and not DATE_RE.match(k["date"]):
                    fails.append(f"{tag}: date '{k['date']}' not 'D Month YYYY', 'Month YYYY' or 'YYYY'")
                if k["date"] == "Undated":
                    fails.append(f"{tag}: shows 'Undated' (a missing date is left out)")
                if not k["badge"]:
                    fails.append(f"{tag}: no .card-kind")
                if not k["order"]:
                    fails.append(f"{tag}: title/source/date/kind order wrong")
    if c.fx == "full" and c.exists("bibliography"):
        with c.page("bibliography") as (pg, _, _):
            cards = pg.evaluate(JS_CARDS)
            if not any(not k["date"] for k in cards if not k["empty"]):
                fails.append("bibliography: undated fixture news item should show no date at all")
            kinds = {k["badge"].lower() for k in cards if not k["empty"]}
            if not (any("news" in x for x in kinds) and any("commentary" in x for x in kinds)):
                fails.append(f"bibliography: card-kind badges {sorted(kinds)} lack both news and commentary")
    verdict(c, "B12", fails, "every card: title, source, date (full month, or none), type badge, same order")


def b13(c):
    fails, sigs = [], {}
    for s in c.present():
        with c.page(s) as (pg, _, _):
            for a in pg.evaluate(JS_ANCHORS):
                if not a["inMain"] or a["skip"] or a["egg"]:
                    continue
                if a["kind"] not in ("page", "external", "file"):
                    fails.append(f"{s}: main link {a['href'][:40]} has data-link='{a['kind']}'")
                    continue
                absolute = bool(urlparse(a["href"]).netloc)
                is_file = bool(re.search(r"\.(pdf|png|jpe?g|webp|svg|zip)$", a["href"].split("?")[0], re.I))
                want = "external" if absolute else ("file" if is_file else "page")
                if a["kind"] != want:
                    fails.append(f"{s}: link {a['href'][:40]} marked {a['kind']}, looks like {want}")
                cue = (a["before"], a["after"], a["svg"] > 0, a["deco"], a["bstyle"],
                       bool(re.search(r"PDF|opens|external|\u2197|\u2193", a["text"] + a["aria"], re.I)))
                sigs.setdefault(a["kind"], set()).add(cue)
    kinds = list(sigs)
    for i in range(len(kinds)):
        for j in range(i + 1, len(kinds)):
            if sigs[kinds[i]] & sigs[kinds[j]] and len(sigs[kinds[i]]) == 1 and len(sigs[kinds[j]]) == 1:
                fails.append(f"link kinds {kinds[i]} and {kinds[j]} share the same non-colour cue {sigs[kinds[i]]}")
    verdict(c, "B13", fails, f"link kinds present {kinds or 'none'} each tagged and with differing non-colour cues (visual check: MANUAL)")


def static_link_check(c):
    bad = []
    nref = 0
    for f in c.files():
        r = c.rel(f)
        if f.suffix == ".html":
            p = parse_html(f)
            refs = [x[2] for x in p.refs]
            css = p.styles
        elif f.suffix == ".css" and not VENDOR_RE.search(r):
            refs, css = [], [f.read_text(encoding="utf-8", errors="replace")]
        else:
            continue
        for chunk in css:
            refs += re.findall(r"url\(\s*['\"]?([^'\")]+)", chunk)
        for ref in refs:
            ref = ref.strip()
            nref += 1
            u = urlparse(ref)
            if ref.startswith("#") or u.scheme in ("mailto", "tel", "data", "blob") or not ref:
                continue
            if u.scheme in ("http", "https"):
                if not u.netloc or " " in ref:
                    bad.append(f"{r}: bad external URL '{ref[:50]}'")
                continue
            if u.scheme:
                bad.append(f"{r}: scheme '{u.scheme}:' in '{ref[:40]}'")
                continue
            if ref.startswith("//") or ref.startswith("/"):
                bad.append(f"{r}: non-relative link '{ref[:40]}'")
                continue
            tgt = (f.parent / unquote(u.path)).resolve() if u.path else f
            if tgt.is_dir() or u.path.endswith("/"):
                tgt = tgt / "index.html"
            if not tgt.is_file():
                bad.append(f"{r}: dead link '{ref[:50]}'")
    return bad, nref


def b14(c):
    fails = []
    bad, nref = static_link_check(c)
    fails += bad
    empty_fx = c.fx in ("empty", "missing")
    secs = [s for s in c.nav if s != "index"]
    for s in c.present([x for x in secs if x not in c.prose]):
        with c.page(s) as (pg, _, _):
            cards = pg.evaluate(JS_CARDS)
            if not cards:
                fails.append(f"{s}: no cards at all (content or 'On its way' required)")
            empties = [k for k in cards if k["empty"]]
            real = [k for k in cards if not k["empty"]]
            if empty_fx and (real or not empties):
                fails.append(f"{s}: empty fixture should show only 'On its way' cards (real {len(real)}, empty {len(empties)})")
            for k in empties:
                if not k["emptyText"]:
                    fails.append(f"{s}: empty card '{k['title']}' lacks exact text 'On its way'")
                if k["borderStyle"] != "dashed":
                    fails.append(f"{s}: empty card border is {k['borderStyle']}, not dashed")
                if k["spinner"]:
                    fails.append(f"{s}: empty card has a spinner")
                rgb = [tuple(map(int, re.findall(r"\d+", col)[:3])) for col in (k["color"], k["borderColor"])]
                if any(r_ > 150 and g < 80 and b < 80 for r_, g, b in rgb):
                    fails.append(f"{s}: empty card uses an error-red colour")
    if c.exists("index"):
        with c.page("index") as (pg, _, _):
            cards = pg.evaluate(JS_CARDS)
            titles = " | ".join(k["title"].lower() for k in cards)
            for s in secs:
                if c.labels[s].lower() not in titles:
                    fails.append(f"index: no card for section {c.labels[s]}")
            if empty_fx:
                for k in cards:
                    if k["kind"] == "section" and "On its way" not in k["text"]:
                        fails.append(f"index: section card '{k['title']}' should say On its way")
    verdict(c, "B14", fails, f"every section shows content or 'On its way' (dashed, no spinner/red); {nref} refs resolve, none rooted")


def b15(c):
    fails = []
    emoji = re.compile("[\U0001F000-\U0001FAFF\u2600-\u26FF\u2705\u2728\u274C\u2B50\uFE0F]")
    for s in c.present():
        with c.page(s) as (pg, _, _):
            txt = pg.evaluate("() => document.body.innerText")
            m = emoji.search(txt)
            if m:
                fails.append(f"{s}: emoji U+{ord(m.group()):04X}")
    verdict(c, "B15", fails, "no emoji in visible text (neutral palette / no decoration / no motion: MANUAL)")


def b16(c):
    fails = []
    if not c.exists("index"):
        fails.append("index missing")
    else:
        for s in c.present(c.nav):
            with c.page(s) as (pg, _, _):
                navs = pg.evaluate("() => [...document.querySelectorAll('nav a')].map(a => [a.getAttribute('href'), a.textContent.trim()])")
                order = [slug_of(h, c.url(s)) for h, _ in navs]
                labels = [t for _, t in navs]
                if order != c.nav:
                    fails.append(f"{s}: nav order {order} != config {c.nav}")
                if [x.lower() for x in labels] != [c.labels[x].lower() for x in c.nav]:
                    fails.append(f"{s}: nav labels {labels} != config")
                break
    verdict(c, "B16", fails, "nav order and labels equal site-config.json (plain-noun wording: MANUAL)")


# ---------------------------------------------------------------- B17

def b17(c):
    fails = []
    if not c.exists("slideshow"):
        return c.rec("B17", "FAIL", "slideshow.html not built")
    d = c.cfg["slideshow"]["dwell_seconds"]
    if d.get("image", 0) < 6 or d.get("chart", 0) < 6 or d.get("text_heavy", 0) < 10:
        fails.append(f"dwell too short {d}")
    with c.page("slideshow", query="?auto=0") as (pg, _, _):
        if not pg.locator("#slideshow").count():
            return c.rec("B17", "FAIL", "no #slideshow on slideshow page")
        cn = counter(pg)
        if not cn:
            return c.rec("B17", "FAIL", "no .slide-counter in 'n / N' form")
        n_total = cn[1]
        if n_total < 2:
            return c.rec("B17", "FAIL", f"fixture should give >=2 slides, counter says {cn}")
        for act in ("pause", "prev", "next", "fullscreen", "exit"):
            if not pg.locator(f"#slideshow [data-action={act}]").count():
                fails.append(f"missing [data-action={act}]")
        ta = pg.evaluate("() => getComputedStyle(document.querySelector('#slideshow .slide-stage') || document.body).touchAction")
        if "pan-y" not in ta:
            fails.append(f"touch-action is '{ta}', not pan-y")
        order = []
        for _ in range(25):
            pg.keyboard.press("Tab")
            r = pg.evaluate(JS_FOCUS)
            if r and r.get("insideSlideshow"):
                order.append(r["action"])
                break
        if not order or order[0] != "pause":
            fails.append(f"first focusable in #slideshow is '{order[:1]}', not pause")
        btn = pg.locator("#slideshow [data-action=pause]").first
        l0 = (btn.inner_text() + (btn.get_attribute("aria-label") or "")).strip().lower()
        if "play" not in l0:
            fails.append(f"?auto=0 should start paused (label '{l0}')")
        pg.keyboard.press("ArrowRight")
        if counter(pg) != (2, n_total):
            fails.append(f"ArrowRight -> {counter(pg)}")
        pg.keyboard.press("ArrowLeft")
        if counter(pg) != (1, n_total):
            fails.append(f"ArrowLeft -> {counter(pg)}")
        pg.keyboard.press("End")
        if counter(pg) != (n_total, n_total):
            fails.append(f"End -> {counter(pg)}")
        pg.keyboard.press("Home")
        if counter(pg) != (1, n_total):
            fails.append(f"Home -> {counter(pg)}")
        pg.click("#slideshow [data-action=next]")
        if counter(pg) != (2, n_total):
            fails.append(f"Next click -> {counter(pg)}")
        pg.click("#slideshow [data-action=prev]")
        if counter(pg) != (1, n_total):
            fails.append(f"Prev click -> {counter(pg)}")
        pg.evaluate("() => document.activeElement && document.activeElement.blur()")
        pg.keyboard.press("Space")
        l1 = (btn.inner_text() + (btn.get_attribute("aria-label") or "")).strip().lower()
        if l1 == l0 or "pause" not in l1:
            fails.append(f"Space did not flip Play->Pause label ('{l0}' -> '{l1}')")
        pg.click("#slideshow [data-action=pause]")
        if (btn.inner_text() + (btn.get_attribute("aria-label") or "")).strip().lower() != l0:
            fails.append("pause button label does not flip back")
        pg.click("#slideshow [data-action=fullscreen]")
        pg.wait_for_timeout(400)
        fs =pg.evaluate("""() => { const e = document.querySelector('#slideshow'), s = getComputedStyle(e), r = e.getBoundingClientRect();
          return !!document.fullscreenElement || (s.position === 'fixed' && Math.abs(r.height - innerHeight) <= 2); }""")
        if not fs:
            fails.append("fullscreen button neither enters Fullscreen API nor a 100dvh fixed overlay")
    for key in ("exit",) + ("Escape",) * 5:
        if c.exists(origin(c)):
            with c.page(origin(c)) as (pg, _, _):
                start = pg.url
                pg.click('nav a[href$="slideshow.html"]')
                pg.wait_for_load_state("load")
                if key == "exit":
                    pg.click("#slideshow [data-action=exit]")
                else:
                    pg.keyboard.press("Escape")
                try:
                    pg.wait_for_url(start, timeout=3000)
                except Exception:
                    pass
                pg.wait_for_timeout(200)
                if pg.url != start:
                    fails.append(f"{'Exit button' if key == 'exit' else 'Esc'} led to {pg.url}, not the page we came from")
    wait = c.dwell_wait()
    scen = {}
    stack = []
    try:
        def open_scn(name, **kw):
            cm = c.page("slideshow", **kw)
            pg, _, _ = cm.__enter__()
            stack.append(cm)
            scen[name] = pg
            return pg
        p = open_scn("reduced", reduced=True)
        p = open_scn("auto0", query="?auto=0")
        p = open_scn("hover")
        p.mouse.move(MOBILE[0] / 2, MOBILE[1] / 2)
        p = open_scn("focus")
        for _ in range(25):
            p.keyboard.press("Tab")
            r = p.evaluate(JS_FOCUS)
            if r and r.get("insideSlideshow"):
                break
        p = open_scn("manual")
        p.click("#slideshow [data-action=pause]")
        geo = r"""() => { const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
          const img = [...document.querySelectorAll('#slideshow img')].find(vis);
          const boxes = [...document.querySelectorAll('#slideshow [data-action]')].filter(vis).map(e => e.getBoundingClientRect());
          if (img) boxes.push(img.getBoundingClientRect());
          const ir = img ? img.getBoundingClientRect() : null;
          const free = [[4, 4], [innerWidth - 4, 4], [4, innerHeight - 4], [innerWidth - 4, innerHeight - 4]].find(pt =>
            !boxes.some(r => pt[0] >= r.left && pt[0] <= r.right && pt[1] >= r.top && pt[1] <= r.bottom));
          return {free: free || null, centre: ir ? [ir.left + ir.width / 2, ir.top + ir.height / 2] : null}; }"""
        p = open_scn("corner", size=(1280, 800))
        g = p.evaluate(geo)
        if g["free"]:
            p.mouse.move(*g["free"])
        else:
            fails.append("no free letterbox point outside image and controls at 1280x800 to test mouse-in-window autoplay")
        p = open_scn("stagehover", size=(1280, 800))
        g = p.evaluate(geo)
        if g["centre"]:
            p.mouse.move(*g["centre"])
        else:
            fails.append("no visible slide image to hover at 1280x800")
        p = open_scn("touch", touch=True)
        cdp = p.context.new_cdp_session(p)
        g = p.evaluate(geo)
        cx, cy = g["centre"] or (MOBILE[0] / 2, MOBILE[1] / 2)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": cx, "y": cy}]})
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        start = {k: counter(v) for k, v in scen.items()}
        pdef = open_scn("default")
        start["default"] = counter(pdef)
        pdef.wait_for_timeout(wait * 1000)
        end = {k: counter(v) for k, v in scen.items()}
        if end["default"] == start["default"]:
            fails.append(f"default did not auto-advance within {wait}s (still {end['default']})")
        for k in ("corner", "touch"):
            if end[k] == start[k]:
                fails.append(f"autoplay stopped with mouse in window outside the stage / after a touch tap ('{k}' still {end[k]})") if k == "corner" else \
                    fails.append(f"autoplay died after a touch tap on the stage (still {end[k]})")
        for k in ("stagehover", "reduced", "auto0", "hover", "focus", "manual"):
            if end[k] != start[k]:
                fails.append(f"'{k}' advanced by itself ({start[k]} -> {end[k]})")
        lab = scen["reduced"].locator("#slideshow [data-action=pause]").first.inner_text().lower()
        if "play" not in lab:
            fails.append(f"reduced-motion should start paused (label '{lab}')")
    finally:
        for cm in reversed(stack):
            try:
                cm.__exit__(None, None, None)
            except Exception:
                pass
    verdict(c, "B17", fails, "pause first/flips, counter, keys, swipe css, fullscreen, exit/Esc, auto-advance, hover/focus/manual/reduced/auto=0 stop it")


# ---------------------------------------------------------------- B18 - B22

def b18(c):
    fails = []
    if not c.exists("media"):
        return c.rec("B18", "FAIL", "media.html not built")
    link = None
    with c.page("media", wait="load") as (pg, reqs, _):
        pg.wait_for_load_state("networkidle")
        if any(re.search(r"plotly[^/]*\.js", u, re.I) for u in reqs):
            fails.append("media page requested Plotly")
        cards = [k for k in pg.evaluate(JS_CARDS) if not k["empty"]]
        figs = [k for k in cards if k["kind"] == "figure"]
        for k in figs:
            if not re.match(r"^Fig\. \d+\b", k["title"]):
                fails.append(f"figure card title '{k['title'][:30]}' lacks 'Fig. N'")
            if not k["imgs"] or any(not a.strip() for a in k["imgAlts"]):
                fails.append(f"'{k['title'][:24]}' image/alt missing")
            if not any(x["kind"] == "file" and re.search(r"\.(png|webp|jpe?g)$", x["href"]) for x in k["links"]):
                fails.append(f"'{k['title'][:24]}' has no link to the full-size image")
            if not re.search(r"Source: .+", k["source"]):
                fails.append(f"'{k['title'][:24]}' has no 'Source: ...' line")
            if c.fx == "real" and not any(x["kind"] == "page" and "bibliography.html#" in x["href"] for x in k["links"]):
                fails.append(f"'{k['title'][:24]}' source does not link to a Bibliography anchor")
        ids = pg.evaluate("() => [...document.querySelectorAll('article.fig-card')].map(a => a.id)")
        if any(not re.fullmatch(r"fig-\d+", i) for i in ids) or len(set(ids)) != len(ids):
            fails.append(f"figure anchors wrong: {ids}")
        for k in cards:
            if k["kind"] == "chart":
                if not k["imgs"] or any(not a.strip() for a in k["imgAlts"]):
                    fails.append(f"chart card '{k['title']}' image/alt missing")
                page_links = [x for x in k["links"] if x["kind"] == "page"]
                if not page_links:
                    fails.append(f"chart card '{k['title']}' has no on-site interactive link")
                elif link is None:
                    link = page_links[0]["href"]
    if link:
        with c.page("media", size=(375, 500), path=urlparse(urljoin(c.url("media"), link)).path.lstrip("/")) as (pg, reqs, _):
            pg.wait_for_selector(".js-plotly-plot", timeout=20000)
            r = pg.evaluate("""() => { const g = document.querySelector('.js-plotly-plot'), c = g._context || {}, l = g._fullLayout || {};
              const axes = Object.keys(l).filter(k => /^[xy]axis/.test(k)); const src = document.querySelector('.chart-source');
              return {scrollZoom: c.scrollZoom, bar: c.displayModeBar, resp: c.responsive, dm: l.dragmode,
                fixed: axes.length > 0 && axes.every(k => l[k].fixedrange), src: src ? src.textContent.trim() : ''}; }""")
            if r["scrollZoom"]:
                fails.append("scrollZoom is on")
            if r["bar"] is not False:
                fails.append(f"displayModeBar is {r['bar']}, not false")
            if r["resp"] is not True:
                fails.append("responsive is not true")
            if r["dm"] is not False and not r["fixed"]:
                fails.append(f"dragmode {r['dm']} and axes not fixedrange")
            if not r["src"]:
                fails.append("no .chart-source line")
    verdict(c, "B18", fails, "media page Plotly-free; figure cards numbered with alt, full-size link, source line to the Bibliography; any chart page locked down")


def b19(c):
    fails = []
    if not c.exists("media"):
        return c.rec("B19", "FAIL", "media.html not built")
    with c.page("media", size=MOBILE, touch=True) as (pg, _, _):
        links = pg.locator("a.fig-image")
        if not links.count():
            if c.fx == "real":
                fails.append("no figure image links on the real build")
            return c.rec("B19", "FAIL" if fails else "PASS", short(fails) if fails else "no figures in this fixture; viewer not applicable")
        pg.wait_for_load_state("networkidle")
        links.first.click()
        pg.wait_for_selector(".viewer:not([hidden])", timeout=5000)
        try:
            pg.wait_for_function("() => document.querySelector('.viewer-img').naturalWidth >= 1600", timeout=8000)
        except Exception:
            pass
        r = pg.evaluate(r"""() => { const v = document.querySelector('.viewer'), st = v.querySelector('.viewer-stage').getBoundingClientRect(),
          b = v.querySelector('.viewer-box').getBoundingClientRect(), i = v.querySelector('.viewer-img'), s = getComputedStyle(v);
          return {bg: s.backgroundColor, fit: b.width <= st.width + 1 && b.height <= st.height + 1, nat: i.naturalWidth, role: v.getAttribute('role'),
                  btns: [...v.querySelectorAll('button')].map(x => { const q = x.getBoundingClientRect(); return [q.width, q.height]; }), w0: b.width}; }""")
        m = re.findall(r"\d+", r["bg"])
        if not m or max(int(x) for x in m[:3]) > 40:
            fails.append(f"viewer backdrop not dark: {r['bg']}")
        if not r["fit"]:
            fails.append("viewer image not fitted to the screen")
        if r["role"] != "dialog":
            fails.append("viewer lacks role=dialog")
        if any(w < 44 or h < 44 for w, h in r["btns"]):
            fails.append("viewer button under 44px")
        if r["nat"] < 1600:
            fails.append(f"viewer image natural width {r['nat']}px (full-size file not loaded)")
        pg.click(".viewer [aria-label='Zoom in']")
        pg.wait_for_timeout(200)
        w1 = pg.evaluate("() => document.querySelector('.viewer-box').getBoundingClientRect().width")
        if w1 <= r["w0"] * 1.2:
            fails.append("Zoom in did not enlarge the image")
        pg.keyboard.press("Escape")
        if pg.evaluate("() => !document.querySelector('.viewer').hidden"):
            fails.append("Esc did not close the viewer")
    verdict(c, "B19", fails, "figure opens a dark, fitted, zoomable viewer with the full-size PNG; Esc closes (pinch: MANUAL)")


def b20(c):
    c.rec("B20", "MANUAL", "scenes page and viewer are checked by checks/check_scenes.py (run: python checks/check_scenes.py --docs docs)")


def b21(c):
    fails = []
    for s in c.present():
        with c.page(s) as (pg, _, _):
            r = pg.evaluate("""() => { const e = [...document.querySelectorAll('a.egg')]; const a = e[0]; if (!a) return {n: 0};
              const b = a.getBoundingClientRect(); return {n: e.length, inFooter: !!a.closest('footer'), inNav: !!a.closest('nav'), w: b.width, h: b.height, href: a.getAttribute('href')}; }""")
            if r["n"] != 1:
                fails.append(f"{s}: {r['n']} a.egg (need 1)")
                continue
            if not r["inFooter"] or r["inNav"]:
                fails.append(f"{s}: egg must be in footer, not nav")
            if r["w"] < 44 or r["h"] < 44:
                fails.append(f"{s}: egg {r['w']:.0f}x{r['h']:.0f} <44")
            if slug_of(r["href"], c.url(s)) != "scenes":
                fails.append(f"{s}: egg href {r['href']} is not scenes")
            pg.focus("a.egg")
            if not pg.evaluate("() => document.activeElement.classList.contains('egg')"):
                fails.append(f"{s}: egg not focusable")
            if s in c.nav and pg.evaluate("() => !!document.querySelector('nav a[href*=scenes]')"):
                fails.append(f"{s}: scenes linked from nav")
    if c.exists("scenes"):
        with c.page("scenes") as (pg, _, _):
            m = pg.evaluate("() => (document.querySelector('meta[name=robots]') || {}).content || ''")
            if "noindex" not in m:
                fails.append(f"scenes: robots meta '{m}' lacks noindex")
    if "scenes" in c.nav:
        fails.append("scenes listed in config sections (must be hidden_pages)")
    verdict(c, "B21", fails, "a.egg in footer on every page, >=44, focusable, not in nav; scenes noindex")


def b22(c):
    fails = []
    url = c.cfg["site"]["public_url"]
    png, svg = c.out / "qr.png", c.out / "qr.svg"
    if not svg.is_file():
        fails.append("qr.svg missing")
    if not png.is_file():
        return c.rec("B22", "FAIL", short(fails + ["qr.png missing"]))
    from PIL import Image
    im = Image.open(png).convert("L")
    if im.size[0] < 1000:
        fails.append(f"qr.png only {im.size[0]}px wide")
    decoded = None
    try:
        import zxingcpp
        res = zxingcpp.read_barcodes(Image.open(png).convert("RGB"))
        decoded = res[0].text if res else None
        if decoded is None:
            fails.append("qr.png did not decode")
        elif decoded != url:
            fails.append(f"qr decodes to '{decoded}', expected '{url}'")
        elif getattr(res[0], "ec_level", "M") not in ("M", "", None):
            fails.append(f"error correction {res[0].ec_level}, expected M")
    except ImportError:
        c.rec("B22-decode", "MANUAL", "zxing-cpp not installed: scan qr.png and confirm it opens the public URL")
    try:
        import segno
        from PIL import ImageOps
        mask = im.point(lambda v: 255 if v < 128 else 0)
        x0, y0, x1, y1 = mask.getbbox()
        mods = segno.make(url, error="m", micro=False).symbol_size(border=0)[0]
        ms = (x1 - x0) / mods
        quiet = min(x0, y0, im.size[0] - x1, im.size[1] - y1) / ms
        if quiet < 3.6:
            fails.append(f"quiet zone ~{quiet:.1f} modules <4")
        if im.getpixel((2, 2)) < 200 or im.getpixel((int(x0 + ms / 2), int(y0 + ms / 2))) > 90:
            fails.append("not dark-on-light")
    except Exception as e:
        fails.append(f"quiet-zone analysis error {e}")
    if c.exists("index"):
        with c.page("index") as (pg, _, _):
            if url not in pg.inner_text("main"):
                fails.append("public URL not printed as text on index")
    verdict(c, "B22", fails, f"qr.png {im.size[0]}px decodes exactly to the public URL, quiet zone/contrast/ECC ok, URL shown as text")


# ---------------------------------------------------------------- B23 - B26

def total_bytes(resps):
    tot = 0
    for r in resps:
        try:
            s = r.request.sizes()
            if s["responseBodySize"] <= 0:
                raise ValueError("size unknown")
            tot += s["responseBodySize"] + max(0, s["responseHeadersSize"])
        except Exception:
            try:
                tot += len(r.body())
            except Exception:
                pass
    return tot


def b23(c):
    fails, notes = [], []
    interactive = set()
    if c.exists("media"):
        with c.page("media") as (pg, _, _):
            for k in pg.evaluate(JS_CARDS):
                for lk in k["links"]:
                    if lk["kind"] == "page" and lk["href"].startswith("charts/"):
                        interactive.add(slug_of(lk["href"], c.url("media")))
    allowed = set(interactive) | {"scenes"}
    for s in c.present():
        with c.page(s) as (pg, reqs, resps):
            pg.wait_for_load_state("networkidle")
            kb = total_bytes(resps) / 1024
            lim = 150 if s == "index" else 1024
            notes.append(f"{s} {kb:.0f}KB")
            if s in ("index",) or s in c.nav:
                if kb > lim:
                    fails.append(f"{s}: {kb:.0f} KB > {lim} KB")
            if s not in allowed and any(re.search(r"plotly|playcanvas", u, re.I) for u in reqs):
                fails.append(f"{s}: loads Plotly/PlayCanvas")
            imgs = pg.evaluate("() => [...document.querySelectorAll('img')].map(i => ({w: i.getAttribute('width'), h: i.getAttribute('height'), lazy: i.loading}))")
            if any(not (i["w"] and i["h"]) for i in imgs):
                fails.append(f"{s}: img without width/height")
            if sum(1 for i in imgs if i["lazy"] != "lazy") > 1:
                fails.append(f"{s}: images not loading=lazy")
    for s in interactive:
        if c.exists(s):
            with c.page(s) as (pg, reqs, _):
                pg.wait_for_load_state("networkidle")
                if not any(re.search(r"plotly", u, re.I) for u in reqs):
                    fails.append(f"{s}: interactive chart page did not load Plotly")
    verdict(c, "B23", fails, "weights ok (" + ", ".join(notes[:8]) + "); Plotly/PlayCanvas only on chart-interactive + scenes; imgs sized+lazy")


def b24(c):
    fails = []
    for s in c.present():
        with c.page(s, js=False) as (pg, _, _):
            if not pg.locator("h1").count():
                fails.append(f"{s}: no h1 without JS")
            txt = pg.inner_text("main").strip() if pg.locator("main").count() else ""
            if len(txt) < 10:
                fails.append(f"{s}: main is empty without JS")
            if s == "slideshow":
                items = pg.locator("main li").count()
                empties = pg.locator(".card--empty").count()
                if c.fx == "full" and items < 2:
                    fails.append(f"slideshow: only {items} list items without JS")
                elif c.fx in ("empty", "missing") and not empties:
                    fails.append("slideshow: no empty-state card without JS")
            if s == "scenes" and pg.locator("main img").count():
                fails.append("scenes: shows images as fallback (rule 9: plain message only)")
    verdict(c, "B24", fails, "JS off: h1 + content on every page; slideshow plain list; scenes plain message")


def b25(c):
    fails = []
    if not (c.out / ".nojekyll").is_file():
        fails.append(".nojekyll missing")
    for s in c.all_slugs:
        if not c.exists(s):
            fails.append(f"{s}.html not written")
    for s in c.present(c.nav):
        if s == "index":
            continue
        with c.page(s) as (pg, _, _):
            if not pg.locator("article.card").count():
                fails.append(f"{s}: neither content nor 'On its way'")
    verdict(c, "B25-output", fails, "build output complete: all pages, .nojekyll, every section has content or 'On its way'")


def scan_text_patterns(data, binary):
    pats = [("user1", rb"(?i)user1"), ("ts.net", rb"(?i)\.ts\.net"), ("tailscale", rb"(?i)tailscale"), ("localhost", rb"(?i)localhost"),
            ("127.0.0.1", rb"127\.0\.0\.1"), ("port 8787/8788", rb":878[78]\b"),
            ("100.x.x.x", rb"\b100\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")]
    if binary:
        pats.append(("drive path", rb"[CDE]:[\\/](Dev|Users|Outputs|Splat|Windows)"))
    else:
        pats += [("drive path", rb"\b[CDE]:[\\/]"), ("file:", rb"(?<![A-Za-z])file:")]
    return [n for n, p in pats if re.search(p, data)]


def b26(c):
    fails = []
    fx_assets = HERE.parent / "tests" / "fixtures" / "assets"
    vendor_skipped = 0
    bad_hashes = {}
    licensed = set()
    if c.fx != "real":
        for n in ("doc-unlicensed.pdf", "poster-unlicensed.pdf", "photo-uncleared.png", "renders/walworth-still.png"):
            if (fx_assets / n).is_file():
                bad_hashes[sha(fx_assets / n)] = n
        for n in ("doc-licensed-print.pdf", "doc-licence-map.pdf", "poster-licensed.pdf"):
            licensed.add(sha(fx_assets / n))
    for f in c.files():
        r = c.rel(f)
        low = r.lower()
        if "renders" in low or "walworth-still" in low:
            fails.append(f"renders-derived file {r}")
        if c.fx != "real" and ("unlicensed" in low or "uncleared" in low):
            fails.append(f"unlicensed/uncleared asset published as {r}")
        if f.suffix == ".sog" or f.stat().st_size > 30_000_000:
            continue
        if f.suffix in (".woff", ".woff2", ".ttf", ".otf", ".eot"):
            fails.append(f"web font {r}")
        digest = None
        if f.suffix in (".pdf", ".png", ".jpg", ".jpeg", ".webp"):
            digest = sha(f)
            if digest in bad_hashes:
                fails.append(f"{r} is a copy of withheld fixture {bad_hashes[digest]}")
            if f.suffix == ".pdf" and c.fx != "real" and digest not in licensed and not VENDOR_RE.search(low):
                fails.append(f"hosted PDF {r} is not a licensed fixture")
        if VENDOR_RE.search(low):
            vendor_skipped += 1
            if f.suffix in (".js", ".css", ".html", ".txt", ".md", ".json"):
                vh = [h for h in scan_text_patterns(f.read_bytes(), True) if h not in ("localhost", "file:")]
                if vh:
                    fails.append(f"{r}: vendor file contains {','.join(vh)}")
            continue
        data = f.read_bytes()
        if f.suffix == ".js":
            ext = re.findall(rb"https?://(?!www\.w3\.org)[A-Za-z0-9.-]+", data)
            if ext:
                fails.append(f"{r}: JS references external host {ext[0].decode()[:40]}")
        hits = scan_text_patterns(data, f.suffix not in (".html", ".css", ".js", ".svg", ".json", ".txt", ".xml", ".webmanifest"))
        if hits:
            fails.append(f"{r}: contains {','.join(hits)}")
        if f.suffix == ".html":
            txt = data.decode("utf-8", "replace")
            for needle in ("Fixture caption (NOT cleared)", "Fixture photo title (NOT cleared)", "Fixture render", "Fixture why-text"):
                if needle in txt:
                    fails.append(f"{r}: shows withheld item '{needle}'")
            p = parse_html(f)
            for tag, key, val in p.refs:
                if re.match(r"https?://", val) and tag != "a" and (key != "href" or (tag == "link" and urlparse(val).netloc != urlparse(c.cfg["site"]["public_url"]).netloc)):
                    fails.append(f"{r}: external {tag}[{key}] {val[:50]}")
            for chunk in p.styles:
                if re.search(r"url\(\s*['\"]?https?:|@import", chunk):
                    fails.append(f"{r}: inline CSS pulls external resource")
        if f.suffix == ".css" and re.search(r"url\(\s*['\"]?https?:|@import\s+(url\()?['\"]?https?:", data.decode("utf-8", "replace")):
            fails.append(f"{r}: CSS pulls external resource")
    for s in c.present():
        with c.page(s) as (pg, reqs, _):
            try:
                pg.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            ext = [u for u in reqs if not u.startswith(c.base) and not u.startswith(("data:", "blob:"))]
            if ext:
                fails.append(f"{s}: non-relative network request {ext[0][:60]}")
    verdict(c, "B26", fails, f"no local paths/internal hosts/CDNs/fonts/renders/uncleared/unlicensed in {len(c.files())} files ({vendor_skipped} vendor files text-skipped)")


# ---------------------------------------------------------------- extra: data routing and prose guard

def data_routing(c):
    if c.fx != "full":
        return
    fails = []

    def cards(slug):
        with c.page(slug) as (pg, _, _):
            return {k["title"]: k for k in pg.evaluate(JS_CARDS)}
    d = cards("bibliography") if c.exists("bibliography") else {}
    a = d.get("Fixture document A")
    if not a or not any(l["kind"] == "file" for l in a["links"]):
        fails.append("bibliography: licensed item A should be a hosted PDF link")
    if "Fixture print item without URL or licence" in d and any(l["kind"] == "file" for l in d["Fixture print item without URL or licence"]["links"]):
        fails.append("bibliography: unlicensed item must not be hosted")
    b = d.get("Fixture document B (no licence)")
    if not b or any(l["kind"] == "file" for l in b["links"]) or not any(l["kind"] == "external" for l in b["links"]):
        fails.append("bibliography: B (no licence) must be an external link only, not hosted")
    cc = d.get("Fixture document C (licence by map)")
    if not cc or not any(l["kind"] == "file" for l in cc["links"]):
        fails.append("bibliography: C (licence_map) should be hosted")
    dd = d.get("Fixture link document (no date)")
    if not dd or dd["date"] != "" or not any(l["kind"] == "external" for l in dd["links"]):
        fails.append("bibliography: use=link item should be external with no date shown")
    if a and a["date"] != "29 August 2016":
        fails.append(f"bibliography: A has a date key, expected '29 August 2016', got '{a['date']}'")
    for t in ("Fixture news article", "Fixture commentary piece", "Fixture undated news item"):
        if t not in d or not any(l["kind"] == "external" for l in d[t]["links"]):
            fails.append(f"bibliography: '{t}' missing or not an external link")
    if c.exists("handouts") and "http-equiv" not in (c.out / "handouts.html").read_text(encoding="utf-8"):
        fails.append("handouts page must not exist as content (redirect stub only)")
    c.rec("DATA", "FAIL" if fails else "PASS", short(fails) if fails else "full fixture routes whole_files/news into the Bibliography per the licence and use rules")


def prose_guard(c):
    if c.fx not in ("full", "half"):
        return
    corpus = []

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            corpus.append(o)
    walk(c.sel)
    walk(c.cfg["site"])
    walk(c.cfg["sections"])
    walk(c.cfg.get("hidden_pages", []))
    norm = lambda t: re.sub(r"\s+", " ", t).strip().lower()
    for row in list(c.sel.get("charts_ready", [])) + list(c.sel.get("charts_tweak", [])):
        gf = Path(c.cfg.get("chart_gallery_dir", "")) / (str(row.get("id", "")) + ".html")
        if gf.is_file():
            raw = gf.read_text(encoding="utf-8", errors="replace")
            raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
            corpus.append(re.sub(r"<[^>]+>", " ", raw))
            corpus.append(gf.read_text(encoding="utf-8", errors="replace"))
            corpus += re.findall(r"""(?:title|source|subtitle)['"]?\s*[:=]\s*['"]([^'"]{6,})['"]""", gf.read_text(encoding="utf-8", errors="replace"))
    blob = norm(" || ".join(corpus + ["Printed copy at the talk", "On its way"]))
    fails = []
    for s in c.present():
        with c.page(s) as (pg, _, _):
            texts = pg.evaluate("""() => [...document.querySelectorAll('p,li,figcaption,dd,blockquote,h2,h3,h4')].filter(e =>
              !e.closest('.card-title,.card-meta,.card-kind,.chart-source,.slide-title,.card-empty-text,nav,.skip-link,article.card[data-kind=chart]')).map(e => e.innerText.trim())""")
            for t in (ln for blk in texts for ln in blk.splitlines()):
                if re.match(r"^(source|data)\s*:", t.strip(), re.I):
                    continue
                if len(t.split()) >= 6 and norm(t) not in blob:
                    fails.append(f"{s}: '{t[:60]}'")
    c.rec("R1", "FAIL" if fails else "PASS",
          short(fails) if fails else "no >=6-word prose outside fixture/config strings (heuristic; wording of controls: MANUAL)")


MATRIX = [(320, 568), (375, 667), (414, 896), (768, 1024), (1024, 768), (812, 375), (1280, 800), (1440, 900), (1920, 1080)]
SMALL_MATRIX = [(375, 667), (1280, 800)]


def matrix(c):
    return MATRIX if c.fx == "full" else SMALL_MATRIX


def site_css(c):
    out = []
    for f in c.files():
        r = c.rel(f)
        if VENDOR_RE.search(r):
            continue
        if f.suffix == ".css":
            out.append((r, f.read_text(encoding="utf-8", errors="replace")))
        elif f.suffix == ".html":
            out.append((r, "\n".join(parse_html(f).styles)))
    return out


def b27(c):
    fails = []
    js = r"""() => { const bad = []; const vw = innerWidth;
      for (const e of document.querySelectorAll('body *')) { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
        if (r.width === 0 || r.height === 0 || s.display === 'none' || s.position === 'fixed' && r.right <= 0) continue;
        if (r.right > vw + 0.5) { let p = e.parentElement, scroller = false; while (p) { const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll' || o === 'hidden') { scroller = true; break; } p = p.parentElement; }
          if (!scroller) bad.push(e.tagName.toLowerCase() + (e.className ? '.' + String(e.className).split(' ')[0] : '') + ' right=' + Math.round(r.right)); } }
      return {sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, bad: bad.slice(0, 3), n: bad.length}; }"""
    for size in matrix(c):
        for s in c.present():
            with c.page(s, size) as (pg, _, _):
                r = pg.evaluate(js)
                if r["sw"] > r["cw"]:
                    fails.append(f"{s}@{size[0]}x{size[1]}: scrollWidth {r['sw']}>{r['cw']}")
                if r["n"]:
                    fails.append(f"{s}@{size[0]}x{size[1]}: {r['n']} elements past right edge {r['bad']}")
    verdict(c, "B27", fails, f"no overflow / element past right edge on {len(c.present())} pages at {len(matrix(c))} sizes")


def b28(c):
    if c.fx != "full":
        return
    fails = []
    need = {375: 1, 768: 2, 1280: 3, 1920: 4}
    js = r"""() => { const cards = [...document.querySelectorAll('article.card')].filter(a => { const r = a.getBoundingClientRect(); return a.offsetParent !== null && getComputedStyle(a).display !== 'none' && r.width > 0 && r.height > 0; }); const groups = new Map();
      cards.forEach(a => { const r = a.getBoundingClientRect(); if (!groups.has(a.parentElement)) groups.set(a.parentElement, []); groups.get(a.parentElement).push(r.width); });
      let ratio = 1; groups.forEach(ws => { if (ws.length > 1) ratio = Math.max(ratio, Math.max(...ws) / Math.min(...ws)); });
      return {n: cards.length, lefts: new Set(cards.map(a => Math.round(a.getBoundingClientRect().left))).size, ratio: ratio}; }"""
    big_page = False
    for s in c.present():
        if s == "slideshow":
            continue
        for w, h in ((375, 667), (768, 1024), (1280, 800), (1920, 1080)):
            with c.page(s, (w, h)) as (pg, _, _):
                r = pg.evaluate(js)
                if r["n"] < 3:
                    break
                if r["n"] >= 4:
                    big_page = True
                want = need[w] if (r["n"] >= 4 or w == 375) else min(need[w], r["n"])
                if w == 375 and r["lefts"] != 1:
                    fails.append(f"{s}@375: {r['lefts']} columns, want 1")
                elif w != 375 and r["lefts"] < want:
                    fails.append(f"{s}@{w}: {r['lefts']} columns, want >={want} ({r['n']} cards)")
                if r["ratio"] > 2.001:
                    fails.append(f"{s}@{w}: widest card {r['ratio']:.1f}x the narrowest")
    if not big_page:
        fails.append("no page has >=4 cards in the full fixture; cannot test 4 columns")
    css = site_css(c)
    if any("auto-fit" in t for _, t in css):
        fails.append("CSS uses auto-fit (must be auto-fill)")
    if not any("auto-fill" in t for _, t in css):
        fails.append("no auto-fill grid in site CSS")
    verdict(c, "B28", fails, "cards go 1/2/3/4 columns at 375/768/1280/1920 (capped by card count), auto-fill, no card >2x narrowest")


def b29(c):
    fails = []
    pages = c.present()
    for s in pages:
        with c.page(s, (1920, 1080)) as (pg, _, _):
            r = pg.evaluate(r"""() => { const rem = parseFloat(getComputedStyle(document.documentElement).fontSize); let maxw = 0, who = '';
              for (const e of document.querySelectorAll('main p, main .card-meta')) { const w = e.getBoundingClientRect().width; if (w > maxw) { maxw = w; who = e.tagName + '.' + e.className; } }
              const m = document.querySelector('main'), cs = getComputedStyle(m);
              const els = [...document.querySelectorAll('main h1, main .card, main p')].map(e => e.getBoundingClientRect()).filter(r => r.width > 0);
              const l = Math.min(...els.map(r => r.left)), rr = Math.max(...els.map(r => r.right));
              return {maxrem: maxw / rem, who: who, pad: Math.max(parseFloat(cs.paddingLeft), parseFloat(cs.paddingRight)), l: l, r: innerWidth - rr}; }""")
            if r["maxrem"] > 45.01:
                fails.append(f"{s}@1920: {r['who']} is {r['maxrem']:.0f}rem wide (>45)")
            if abs(r["l"] - r["r"]) > 4:
                fails.append(f"{s}@1920: content not centred (left {r['l']:.0f}, right {r['r']:.0f})")
            if r["pad"] > 64:
                fails.append(f"{s}@1920: main padding {r['pad']:.0f}px >64")
        with c.page(s, (320, 568)) as (pg, _, _):
            r = pg.evaluate(r"""() => { const els = [...document.querySelectorAll('main h1, main .card, main p')].map(e => e.getBoundingClientRect()).filter(r => r.width > 0);
              return {l: Math.min(...els.map(r => r.left)), r: innerWidth - Math.max(...els.map(r => r.right))}; }""")
            if r["l"] < 11.5 or r["r"] < 11.5:
                fails.append(f"{s}@320: gutter {r['l']:.0f}/{r['r']:.0f}px <12")
    verdict(c, "B29", fails, "measure <=45rem at 1920, centred, gutters >=12px at 320 and main padding <=64px at 1920")


def b30(c):
    fails = []
    for r, t in site_css(c):
        for m in re.finditer(r"font-size\s*:\s*([^;}]+)", t):
            v = m.group(1).strip()
            if re.search(r"\d\s*px\b", v) and "clamp" not in v:
                fails.append(f"{r}: font-size {v[:30]} in px")
            cm = re.match(r"clamp\(\s*([^,]+),\s*[^,]+,\s*([^)]+)\)", v)
            if cm:
                lo, hi = cm.group(1).strip(), cm.group(2).strip()
                un = lambda x: re.match(r"^([\d.]+)(rem|em)$", x)
                if not (un(lo) and un(hi)):
                    fails.append(f"{r}: clamp bounds not rem/em: {v[:40]}")
                elif float(un(hi).group(1)) < 1.25 * float(un(lo).group(1)):
                    fails.append(f"{r}: clamp max <1.25x min: {v[:40]}")
    with c.page("index", (320, 568)) as (pg, _, _):
        fs = pg.evaluate("() => parseFloat(getComputedStyle(document.body).fontSize)")
        if fs < 16:
            fails.append(f"body font-size {fs}px at 320 <16")
    for s in (c.present() if c.fx == "full" else c.present(["index", "bibliography"])):
        with c.page(s, (1280, 800)) as (pg, _, _):
            pg.evaluate("() => { document.documentElement.style.fontSize = '200%'; }")
            pg.wait_for_timeout(200)
            r = pg.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
            if r[0] > r[1]:
                fails.append(f"{s}: overflow at 200% text zoom ({r[0]}>{r[1]})")
    verdict(c, "B30", fails, "no px font-sizes, clamp bounds rem with max>=1.25x min, body>=16px at 320, no overflow at 200% zoom")


def b31(c):
    fails = []
    js = r"""() => { const l = [...document.querySelectorAll('nav a')].filter(a => a.getBoundingClientRect().width > 0);
      const tops = new Set(l.map(a => Math.round(a.getBoundingClientRect().top))); return {n: l.length, rows: tops.size}; }"""
    for s in c.present(["index", "media"]):
        for size, want in (((1280, 800), 1), ((1920, 1080), 1), ((360, 740), 3)):
            with c.page(s, size) as (pg, _, _):
                r = pg.evaluate(js)
                if r["n"] != len(c.nav):
                    fails.append(f"{s}@{size[0]}: {r['n']} visible nav links, want {len(c.nav)}")
                if r["rows"] > want:
                    fails.append(f"{s}@{size[0]}: nav on {r['rows']} rows (max {want})")
    verdict(c, "B31", fails, "nav one row at >=1280, <=3 rows with all links visible at 360")


def b32(c):
    fails = []
    for s in c.present():
        with c.page(s, MOBILE) as (pg, _, _):
            pg.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            pg.wait_for_timeout(500)
            for i in pg.evaluate(r"""() => [...document.querySelectorAll('img')].map(i => ({src: (i.getAttribute('src') || '').slice(-30), w: i.getAttribute('width'), h: i.getAttribute('height'),
              ar: getComputedStyle(i).aspectRatio, srcset: !!i.getAttribute('srcset'), sizes: i.getAttribute('sizes') || '', nat: i.naturalWidth, css: i.getBoundingClientRect().width}))"""):
                if not ((i["w"] and i["h"]) or i["ar"] not in ("auto", "")):
                    fails.append(f"{s}: img {i['src']} has no width/height or aspect-ratio")
                if i["srcset"] and (not i["sizes"] or "%" in i["sizes"]):
                    fails.append(f"{s}: img {i['src']} srcset needs sizes without %")
                if i["css"] > 0 and i["nat"] > 3 * i["css"] * 1.001:
                    fails.append(f"{s}: img {i['src']} natural {i['nat']}px > 3x css {i['css']:.0f}px")
    for s in c.present(["media", "bibliography", "slideshow"]):
        for size in (MOBILE, (1280, 800)):
            ctx = c.browser.new_context(viewport={"width": size[0], "height": size[1]})
            pg = ctx.new_page()
            try:
                pg.add_init_script("window.__cls = 0; new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; }).observe({type: 'layout-shift', buffered: true});")
                pg.goto(c.url(s) + "?auto=0")
                pg.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                pg.wait_for_timeout(1000)
                cls = pg.evaluate("() => window.__cls")
                if cls > 0.1:
                    fails.append(f"{s}@{size[0]}: CLS {cls:.3f} >0.1")
            finally:
                ctx.close()
    verdict(c, "B32", fails, "imgs sized, srcset has sizes (no %), natural <=3x css width at 375, CLS <=0.1 on media/bibliography/slideshow")


def b33(c):
    fails = []
    if c.exists("slideshow"):
        for size in ((1920, 1080), (812, 375)):
            with c.page("slideshow", size, query="?auto=0") as (pg, _, _):
                r = pg.evaluate(r"""() => { const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden'; };
                  const img = [...document.querySelectorAll('#slideshow img')].find(vis);
                  const ctl = [...document.querySelectorAll('#slideshow [data-action]')].filter(vis).map(e => { const r = e.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth; });
                  const cap = [...document.querySelectorAll('#slideshow .slide-title, #slideshow figcaption, #slideshow .slide-caption')].find(vis);
                  if (!img) return {noimg: true, cap: cap ? parseFloat(getComputedStyle(cap).fontSize) : 0};
                  const r = img.getBoundingClientRect();
                  return {inside: r.top >= -0.5 && r.left >= -0.5 && r.bottom <= innerHeight + 0.5 && r.right <= innerWidth + 0.5, fit: getComputedStyle(img).objectFit,
                    ratio: (r.width / r.height) / (img.naturalWidth / img.naturalHeight), ctl: ctl.length > 0 && ctl.every(Boolean), nctl: ctl.length,
                    cap: cap ? parseFloat(getComputedStyle(cap).fontSize) : 0}; }""")
                tag = f"slideshow@{size[0]}x{size[1]}"
                if r.get("noimg"):
                    if c.fx == "full":
                        fails.append(f"{tag}: no visible slide image")
                    continue
                if not r["inside"]:
                    fails.append(f"{tag}: image not fully inside viewport")
                if r["fit"] != "contain":
                    fails.append(f"{tag}: object-fit is {r['fit']}, not contain")
                if abs(r["ratio"] - 1) > 0.01:
                    fails.append(f"{tag}: image box aspect off natural by {abs(r['ratio'] - 1) * 100:.1f}%")
                if not r["ctl"]:
                    fails.append(f"{tag}: controls not all inside viewport ({r['nctl']} found)")
                if size[0] == 1920 and r["cap"] < 28:
                    fails.append(f"{tag}: slide title/caption {r['cap']}px <28 (needs .slide-title or figcaption)")
    for rel, t in site_css(c):
        for m in re.finditer(r"\{([^{}]*)\}", t):
            blk = m.group(1)
            i = blk.find("100vh")
            if i >= 0 and not re.search(r"100[ds]vh", blk[i + 5:]):
                fails.append(f"{rel}: 100vh with no later dvh/svh line")
    verdict(c, "B33", fails, "slideshow image contained, aspect kept, controls in view, large caption at 1920, no bare 100vh")


BUILD_OUT = {}


def schema_check(c):
    if c.fx not in ("full", "half"):
        return
    import jsonschema
    schema = json.loads((HERE.parent / "schema" / "selections.schema.json").read_text(encoding="utf-8-sig"))
    errs = list(jsonschema.Draft202012Validator(schema).iter_errors(c.sel))
    bad_items = {tuple(list(e.absolute_path)[:2]) for e in errs if len(e.absolute_path) >= 2}
    if c.fx == "full":
        return c.rec("SCHEMA", "FAIL" if errs else "PASS",
                     short(f"{'/'.join(map(str, e.absolute_path))}: {e.message[:60]}" for e in errs) if errs else "full fixture validates against schema/selections.schema.json with zero errors")
    if not bad_items:
        return c.rec("SCHEMA", "FAIL", "half fixture is meant to hold invalid items but validates clean")
    out = BUILD_OUT.get("half")
    if out is None:
        return c.rec("SCHEMA", "MANUAL", "build output not captured (--skip-build): confirm build stdout names each invalid item")
    lines = [l for l in out.splitlines() if re.search(r"invalid|skipped", l, re.I)]
    ok = len(lines) >= len(bad_items)
    c.rec("SCHEMA", "PASS" if ok else "FAIL",
          f"{len(bad_items)} invalid half items, {len(lines)} build stdout lines mention invalid/skipped" +
          ("" if ok else "; each invalid item needs its own line"))


MANUAL = [
    ("B12-visual", "Cards line up: title, then one metadata line in the same place on every page."),
    ("B13-visual", "Page / external / file links look different with colour removed (greyscale screenshot)."),
    ("B15", "Neutral background, one accent hue + greys, no decorative imagery, no motion except slideshow and loaders."),
    ("B16-labels", "Section labels are plain nouns."),
    ("B17-swipe", "Real phone: horizontal swipe changes slides while vertical swipe still scrolls."),
    ("B19-pinch", "Real phone: full-size poster/page image can be pinch-zoomed."),
    ("B20-hint", "Scenes: gesture hint wording, WebGL-missing and load-failure messages are plain text."),
    ("B22-scan", "Real phone camera scans qr.png and opens the live address."),
    ("R1-wording", "Controls and labels contain no Jared-voice or builder-written prose (hard rule 1)."),
]

CHECKS = [("B1", b1), ("B2", b2), ("B3", b3), ("B4", b4), ("B5", b5), ("B6", b6), ("B7", b7), ("B8", b8), ("B9", b9),
          ("B10", b10), ("B11", b11), ("B12", b12), ("B13", b13), ("B14", b14), ("B15", b15), ("B16", b16),
          ("B17", b17), ("B18", b18), ("B19", b19), ("B20", b20), ("B21", b21), ("B22", b22), ("B23", b23),
          ("B24", b24), ("B25", b25), ("B26", b26), ("DATA", data_routing), ("R1", prose_guard), ("SCHEMA", schema_check), ("B27", b27), ("B28", b28), ("B29", b29), ("B30", b30),
          ("B31", b31), ("B32", b32), ("B33", b33)]
SINGLE_FIXTURE_ONLY = {"B17": {"full"}, "B18": {"real"}, "B19": {"real"}}


# ---------------------------------------------------------------- driver

class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(directory):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(directory)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def build(root, fx, out, skip):
    if skip:
        return out.is_dir(), "reused existing output" if out.is_dir() else "no existing output to reuse"
    script = root / "build.py"
    if not script.is_file():
        return False, f"build.py not found at {script}"
    if out.exists():
        shutil.rmtree(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fixd = root / "tests" / "fixtures"
    cmd = [sys.executable, str(script)]
    if fx == "missing":
        cmd += ["--selections", str(fixd / "_does_not_exist.json")]
    elif fx != "real":
        cmd += ["--selections", str(fixd / f"selections-{fx}.json")]
    if fx != "real":
        cmd += ["--config-overlay", str(fixd / "site-config.test.json")]
    cmd += ["--out", str(out)]
    t = time.time()
    try:
        r = subprocess.run(cmd, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    except subprocess.TimeoutExpired:
        return False, "build timed out after 900s"
    dt = time.time() - t
    BUILD_OUT[fx] = (r.stdout or "") + "\n" + (r.stderr or "")
    if r.returncode != 0:
        tail = (r.stderr.strip() or r.stdout.strip()).splitlines()[-1:] or [""]
        return False, f"build exit {r.returncode}: {tail[0][:150]}"
    return True, f"build exit 0 in {dt:.1f}s"


def render(results):
    w = max(len(r["id"]) for r in results) if results else 4
    lines = [f"{'CHECK':<{w}}  {'FIXTURE':<8} {'RESULT':<7} EVIDENCE"]
    for r in results:
        lines.append(f"{r['id']:<{w}}  {r['fixture']:<8} {r['status']:<7} {r['evidence'][:150]}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", default="all", choices=ALL_FIXTURES + ["all"])
    ap.add_argument("--only", default="")
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument("--root", default=str(HERE.parent))
    a = ap.parse_args()
    root = Path(a.root).resolve()
    only = {x.strip().upper() for x in a.only.split(",") if x.strip()}
    fxs = ALL_FIXTURES if a.fixture == "all" else [a.fixture]
    results = []
    base_cfg = json.loads((root / "site-config.json").read_text(encoding="utf-8-sig"))
    overlay = json.loads((root / "tests/fixtures/site-config.test.json").read_text(encoding="utf-8-sig"))
    to_run = []
    for fx in fxs:
        out = HERE / "_out" / fx / "site"
        ok, msg = build(root, fx, out, a.skip_build)
        if not only or "B25" in only:
            results.append({"id": "B25", "fixture": fx, "status": "PASS" if ok else "FAIL", "evidence": msg})
        if ok:
            to_run.append((fx, out))
        else:
            results.append({"id": "ALL", "fixture": fx, "status": "FAIL", "evidence": "checks not run: no build output"})
    if to_run:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge")
            for fx, out in to_run:
                cfg = base_cfg if fx == "real" else deep_merge(base_cfg, overlay)
                sel = {}
                sp = root / "tests/fixtures" / f"selections-{fx}.json"
                if fx in ("empty", "half", "full") and sp.is_file():
                    sel = json.loads(sp.read_text(encoding="utf-8-sig"))
                srv, base = serve(out)
                c = Ctx(fx, out, cfg, sel, browser, base, only, results)
                try:
                    for cid, fn in CHECKS:
                        if cid in SINGLE_FIXTURE_ONLY and fx not in SINGLE_FIXTURE_ONLY[cid]:
                            continue
                        if only and cid not in only:
                            continue
                        t = time.time()
                        if not c.present() and cid not in ("SCHEMA",):
                            c.rec(cid, "FAIL", "no pages were built, nothing to check")
                            continue
                        try:
                            fn(c)
                        except Exception as e:
                            tb = traceback.extract_tb(sys.exc_info()[2])[-1]
                            c.rec(cid, "FAIL", f"check crashed: {type(e).__name__}: {str(e)[:120]} (line {tb.lineno})")
                        print(f"  [{fx}] {cid} done {time.time() - t:.1f}s", flush=True)
                finally:
                    srv.shutdown()
            browser.close()
    if not only:
        for cid, what in MANUAL:
            results.append({"id": cid, "fixture": "-", "status": "MANUAL", "evidence": what})
    # checks that only apply to some fixtures leave no row for the others; that is intended
    rep = HERE / "_out"
    rep.mkdir(exist_ok=True)
    (rep / "report.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    md = ["# NHC16-LFR check report", "", "| check | fixture | result | evidence |", "|---|---|---|---|"]
    md += [f"| {r['id']} | {r['fixture']} | {r['status']} | {r['evidence'].replace('|', '/')} |" for r in results]
    (rep / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(render(results))
    fails = [r for r in results if r["status"] == "FAIL"]
    print(f"\n{len(results)} rows: {sum(r['status'] == 'PASS' for r in results)} PASS, {len(fails)} FAIL, "
          f"{sum(r['status'] == 'MANUAL' for r in results)} MANUAL. Reports in {rep}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
