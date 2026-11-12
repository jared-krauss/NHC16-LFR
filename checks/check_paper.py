"""Standalone check of the Paper page, built against a placeholder fixture paper (never the real paper.md).

    python checks/check_paper.py [--shots DIR] [--keep-real]

Builds tests/fixtures/paper/paper-fixture.md into checks/_out/paper/site with NHC_PAPER_SOURCE, then checks at 390x844 and
1440x900: figure references become links (existing numbers only, ranges linked per number, Fig. 9 left as text and warned
about), every link resolves to media.html#fig-N, a tap opens the right figure in the viewer on the Paper page, Escape
closes it back to the same scroll position, the menu lists every figure and section, opens and closes with Escape with
focus handled, tap targets are at least 44 px, no horizontal overflow, and the old talk title appears nowhere in the build.
Exits 1 on any failure.
"""
import argparse
import functools
import http.server
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
FIXTURE = ROOT / "tests" / "fixtures" / "paper" / "paper-fixture.md"
OUT = ROOT / "checks" / "_out" / "paper" / "site"
OLD_TITLE = "Live Facial Recognition at Notting Hill Carnival: The Met"
VIEWPORTS = [("390", 390, 844), ("1440", 1440, 900)]
FAILS = []
NFIG = len(json.loads((ROOT / "figures-config.json").read_text(encoding="utf-8"))["figures"])


def ok(cond, msg):
    """Record one check result."""
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)
    return cond


def serve(docs):
    """Serve docs on a free local port; returns (server, base_url)."""
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(docs)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def build_fixture():
    """Build the fixture paper into OUT; returns the build's stdout."""
    env = dict(os.environ, NHC_PAPER_SOURCE=str(FIXTURE))
    r = subprocess.run([PY, str(ROOT / "build.py"), "--out", str(OUT)], cwd=ROOT, env=env, capture_output=True,
                       text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


def static_checks(log):
    """Checks that need no browser."""
    html = (OUT / "paper.html").read_text(encoding="utf-8")
    nfig = len(json.loads((ROOT / "figures-config.json").read_text(encoding="utf-8"))["figures"])
    refs = [int(n) for n in re.findall(r'class="fig-ref"[^>]*href="media\.html#fig-(\d+)"[^>]*data-fig="\d+"', html)]
    want = [n for n in (1, 3, 2, 3, 4, 5) if n <= nfig]
    ok(refs == want, f"fixture references linked in order, existing figures only (want {want}, got {refs})")
    ok("Fig. 9" in html and 'data-fig="9"' not in html, "Fig. 9 left as plain text")
    ok("Fig. 9 is not in figures-config.json" in log, "build warns about Fig. 9")
    media = (OUT / "media.html").read_text(encoding="utf-8")
    ok(all(f'id="fig-{n}"' in media for n in set(refs)), "every linked figure has an anchor on media.html")
    ok(html.count('class="pm-num"') == nfig, f"menu lists {nfig} figures (static)")
    hits = [f.name for f in OUT.rglob("*") if f.suffix in (".html", ".js", ".json", ".css")
            and OLD_TITLE in f.read_text(encoding="utf-8", errors="ignore")]
    ok(not hits, f"old talk title absent from the build ({hits})")
    ok(not (ROOT / "paper" / "paper.md").read_text(encoding="utf-8").count("Lorem"), "real paper.md holds no fixture text")


def run_view(p, base, tag, w, h, shots):
    """Browser checks at one viewport."""
    b = p.chromium.launch(channel="msedge")
    ctx = b.new_context(viewport={"width": w, "height": h}, has_touch=w < 700, device_scale_factor=1)
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(base + "/paper.html", wait_until="load")
    pg.wait_for_selector("#paper-menu-btn:not([hidden])")
    ok(pg.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"{tag}: no horizontal overflow")
    ok(pg.evaluate("getComputedStyle(document.querySelector('.paper p')).maxWidth") != "none"
       or pg.evaluate("document.querySelector('.paper p').getBoundingClientRect().width") <= 1300, f"{tag}: readable measure")
    pg.screenshot(path=str(shots / f"paper-{tag}.png"))

    pg.evaluate("document.querySelector('a[data-fig=\"4\"]').scrollIntoView({block:'center'})")
    y = pg.evaluate("scrollY")
    ok(y > 100, f"{tag}: scrolled down to a reference (y={y})")
    link = pg.locator('.paper a[data-fig="3"]').first
    link.scroll_into_view_if_needed()
    y = pg.evaluate("scrollY")
    link.click()
    pg.wait_for_selector(".viewer:not([hidden])")
    label = pg.inner_text(".viewer-label")
    ok(label.startswith("Fig. 3"), f"{tag}: tapping Figure 3 opens Fig. 3 in the viewer ('{label[:30]}')")
    ok(pg.url.split("/")[-1].split("#")[0] == "paper.html", f"{tag}: stayed on the Paper page")
    pg.wait_for_timeout(600)
    pg.screenshot(path=str(shots / f"paper-{tag}-viewer.png"))
    pg.keyboard.press("ArrowRight")
    ok(pg.inner_text(".viewer-label").startswith("Fig. 4"), f"{tag}: viewer next goes to Fig. 4")
    pg.keyboard.press("Escape")
    pg.wait_for_selector(".viewer", state="hidden")
    y2 = pg.evaluate("scrollY")
    ok(abs(y2 - y) <= 2, f"{tag}: closing returns to the same scroll position ({y} -> {y2})")

    btn = pg.locator("#paper-menu-btn")
    bb = btn.bounding_box()
    ok(bb["width"] >= 44 and bb["height"] >= 44, f"{tag}: menu button >= 44px ({bb['width']:.0f}x{bb['height']:.0f})")
    ok(bb["y"] + bb["height"] <= h and bb["x"] + bb["width"] <= w, f"{tag}: menu button inside the viewport")
    btn.click()
    pg.wait_for_selector("#paper-menu:not([hidden])")
    figs = pg.locator("#paper-menu .pm-list a[data-fig]")
    ok(figs.count() == NFIG, f"{tag}: menu lists {NFIG} figures (got {figs.count()})")
    ok(pg.locator("#paper-menu a[data-jump]").count() == 3, "%s: menu lists 3 section headings" % tag)
    ok(pg.locator('#paper-menu a[href="media.html"]').count() == 1, f"{tag}: menu has All figures link")
    small = pg.evaluate("""() => [...document.querySelectorAll('#paper-menu a, #paper-menu button')]
        .filter(e => e.getBoundingClientRect().height < 43.5).map(e => e.textContent.trim().slice(0, 20))""")
    ok(not small, f"{tag}: menu tap targets >= 44px ({small})")
    inside = pg.evaluate("document.getElementById('paper-menu').contains(document.activeElement)")
    ok(inside, f"{tag}: focus moves into the menu")
    pg.screenshot(path=str(shots / f"paper-{tag}-menu.png"))
    pg.keyboard.press("Escape")
    ok(pg.locator("#paper-menu").is_hidden(), f"{tag}: Escape closes the menu")
    ok(pg.evaluate("document.activeElement.id") == "paper-menu-btn", f"{tag}: focus returns to the menu button")

    btn.click()
    pg.locator('#paper-menu a[data-fig="2"]').click()
    pg.wait_for_selector(".viewer:not([hidden])")
    ok(pg.inner_text(".viewer-label").startswith("Fig. 2"), f"{tag}: menu figure opens Fig. 2 in the viewer")
    ok(pg.locator("#paper-menu").is_hidden(), f"{tag}: menu closed behind the viewer")
    pg.keyboard.press("Escape")
    pg.wait_for_selector(".viewer", state="hidden")
    ok(abs(pg.evaluate("scrollY") - y) <= 2, f"{tag}: scroll position kept after menu-opened viewer")

    btn.click()
    pg.locator("#paper-menu a[data-jump]").nth(1).click()
    pg.wait_for_timeout(300)
    ok(pg.locator("#paper-menu").is_hidden() and pg.url.endswith("#second-section"), f"{tag}: section jump closes menu and moves to the heading")
    ok(pg.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"{tag}: no overflow after interaction")
    ok(not errs, f"{tag}: no page errors ({errs})")
    ctx.close()
    b.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", default=r"E:\Outputs\phd-conference-2026-11-12\_work\paper")
    a = ap.parse_args()
    shots = Path(a.shots)
    shots.mkdir(parents=True, exist_ok=True)
    code, log = build_fixture()
    ok(code == 0, "fixture build succeeds")
    static_checks(log)
    srv, base = serve(OUT)
    try:
        with sync_playwright() as p:
            for tag, w, h in VIEWPORTS:
                run_view(p, base, tag, w, h, shots)
    finally:
        srv.shutdown()
    print(f"{len(FAILS)} failure(s)")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
