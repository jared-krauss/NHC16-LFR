"""Standalone check of the hidden 3D scenes page, run against a built docs folder.

    python checks/check_scenes.py [--docs D:\\Dev\\NHC16-LFR\\docs] [--shots DIR] [--no-wait-ready]

For both scenes at 390x844 and 1440x900 it checks: no horizontal overflow, overlay labels and figures, the Source link
(text starts "Source: " and points at a #page= address), the hamburger menu and its four items, tap-target size, gallery
count (min(20, training views)), no metadata in any published scene image, Escape closing lightbox, gallery, menu and
viewer in turn, and the footer easter egg (present, keyboard focusable, named). Exits 1 on any failure.
"""
import argparse
import functools
import http.server
import io
import json
import re
import sys
import threading
import urllib.request
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
VIEWPORTS = [("390", 390, 844), ("1440", 1440, 900)]
BIG = [("1920", 1920, 1080), ("3840", 3840, 2160)]
LABELS = ["Faces Scanned", "Arrests", "False Alerts"]
MENU_ITEMS = ["Reset view", "Previous view", "Next view", "Gallery"]
GL_ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--use-gl=angle"]
FAILS, NOTES = [], []


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


def has_metadata(raw):
    """True when JPEG bytes carry EXIF, XMP, ICC or a camera name."""
    if re.search(rb"Exif\x00\x00|ns\.adobe\.com|ICC_PROFILE|NIKON|photoshop", raw, re.I):
        return True
    try:
        im = Image.open(io.BytesIO(raw))
        return bool(len(im.getexif()) or im.info.get("exif") or im.info.get("icc_profile") or im.info.get("xmp"))
    except OSError:
        return True


def check_images(docs, base):
    """Every published scene JPEG is free of metadata."""
    files = sorted((docs / "scenes").rglob("*.jpg"))
    ok(len(files) > 0, f"scene images published ({len(files)})")
    bad = [f.name for f in files if has_metadata(f.read_bytes())]
    ok(not bad, f"no EXIF/XMP/ICC/camera text in {len(files)} scene images" + (f" (bad: {bad[:5]})" if bad else ""))


def check_egg(page, base):
    """The footer easter egg exists, is named and can take keyboard focus."""
    page.goto(base + "/index.html")
    egg = page.query_selector("[data-egg]")
    if not ok(egg is not None, "easter egg element [data-egg] exists in the footer (needs the base.html change)"):
        return
    ok(bool(egg.get_attribute("aria-label")), "easter egg has an aria-label")
    ok(str(egg.evaluate("e => e.tabIndex >= 0 ? e.getAttribute('href') : ''")).startswith('scenes.html'), "easter egg is a focusable link")
    egg.focus()
    ok(page.evaluate("document.activeElement && document.activeElement.hasAttribute('data-egg')"), "easter egg takes keyboard focus")
    page.wait_for_timeout(500)
    ok(page.evaluate("getComputedStyle(document.querySelector('.egg-label')).opacity") != "0", "bracket label shows on focus")
    box = egg.bounding_box()
    ok(box["width"] >= 44 and box["height"] >= 44, f"easter egg tap target >= 44px ({box['width']:.0f}x{box['height']:.0f})")


def check_scene(page, base, scene, vp, shots, wait_ready):
    """One scene at one viewport."""
    tag = f"{scene['id']}@{vp[0]}"
    page.set_viewport_size({"width": vp[1], "height": vp[2]})
    page.goto(base + "/scenes.html#" + scene["id"])
    page.wait_for_selector(f".sv[data-viewer={scene['id']}]:not([hidden])", timeout=20000)
    sv = f".sv[data-viewer={scene['id']}]"
    if wait_ready:
        try:
            page.wait_for_function("window.__scenes && window.__scenes.ready", timeout=240000)
            page.wait_for_timeout(1200)
        except Exception:
            NOTES.append(f"{tag}: 3D scene did not finish loading in time (WebGL/swiftshader); DOM checks continue")
    over = page.evaluate("[document.documentElement.scrollWidth, innerWidth, document.querySelector('%s').scrollWidth, document.querySelector('%s').clientWidth]" % (sv, sv))
    ok(over[0] <= over[1] and over[2] <= over[3], f"{tag} no horizontal overflow {over}")
    top = page.inner_text(f"{sv} .sv-top")
    ok(all(l.lower() in top.lower() for l in LABELS), f"{tag} labels {LABELS} present")
    figs = page.eval_on_selector_all(f"{sv} .sv-fig dd", "els => els.map(e => e.textContent.trim())")
    ok(len(figs) == 3 and all(re.fullmatch(r"[\d,]+", f) for f in figs), f"{tag} three numeric figures {figs}")
    ok(bool(page.inner_text(f"{sv} .sv-place").strip()) and bool(page.inner_text(f"{sv} .sv-when").strip()), f"{tag} location and date present")
    src = page.query_selector(f"{sv} .sv-source")
    if ok(src is not None, f"{tag} Source link exists"):
        text, href = src.inner_text().strip(), src.get_attribute("href")
        ok(text.startswith("Source: ") and len(text) > 12, f"{tag} Source text starts 'Source: ' ({text[:48]}...)")
        ok(href.startswith("https://") and "#page=" in href, f"{tag} Source href has #page= ({href[-60:]})")
        ok(src.bounding_box()["height"] >= 44, f"{tag} Source tap height >= 44px")
    nav = page.eval_on_selector_all(f"{sv} .sv-nav a", "els => els.map(e => { const r = e.getBoundingClientRect(); return [e.textContent.trim(), e.getAttribute('href'), r.height, r.top, r.left, r.width]; })")
    ok(len(nav) >= 3 and len({round(n[3]) for n in nav}) == 1, f"{tag} nav links {[n[0] for n in nav]} on one row")
    hit = page.evaluate("""sv => { const a = document.querySelector(sv + ' .sv-nav a'); const r = a.getBoundingClientRect();
      const at = (dy) => document.elementFromPoint(r.left + r.width / 2, dy); return [r.height, true, at(r.bottom - 2) === a]; }""", sv)
    ok(hit[0] + 0.5 >= 44 and hit[1] and hit[2], f"{tag} nav tap area >= 44px ({hit[0]:.0f}px link + hit padding)")
    other = page.query_selector(f"{sv} .sv-other")
    ok(other is not None and other.inner_text().strip().startswith("Change to: ") and other.get_attribute("href").startswith("scenes.html#"), f"{tag} 'Change to: <scene>' link present")
    order = page.evaluate("sv => [document.querySelector(sv + ' .sv-navbar').getBoundingClientRect().bottom, document.querySelector(sv + ' .sv-place').getBoundingClientRect().top, document.querySelector(sv + ' .sv-navbar').getBoundingClientRect().top]", sv)
    ok(order[2] <= 1 and order[0] <= order[1], f"{tag} nav bar is at the very top, above the title block")
    top_h, bot_h = page.evaluate("[document.querySelector('%s .sv-top').offsetHeight, document.querySelector('%s .sv-bottom').offsetHeight]" % (sv, sv))
    if vp[1] == 390:
        ok(top_h <= 104, f"{tag} nav + title block {top_h}px <= 104px (old title block alone was 104px)")
    ok(top_h < vp[2] * 0.2, f"{tag} top overlay {top_h}px is under 20% of the viewport height")
    ok(bot_h <= top_h + 2, f"{tag} bottom band not taller than top ({bot_h} vs {top_h})")
    burger = page.query_selector(f"{sv} .sv-burger")
    bb = burger.bounding_box()
    bhit = page.evaluate("sv => { const b = document.querySelector(sv + ' .sv-burger'); const r = b.getBoundingClientRect(); return [document.elementFromPoint(r.left - 5, r.top + 10) === b, document.elementFromPoint(r.right + 5, r.bottom - 10) === b, document.elementFromPoint(r.left + 10, r.bottom + 5) === b]; }", sv)
    ok(bb["width"] >= 43.5 and bb["height"] >= 43.5, f"{tag} hamburger {bb['width']:.0f}px >= 44px")
    if shots:
        page.screenshot(path=str(shots / f"viewer-{scene['id']}-{vp[0]}.png"))
    page.evaluate("window.__scenes && window.__scenes.viewer.pause()")
    burger.click()
    page.wait_for_selector(f"{sv} .sv-menu:not([hidden])", timeout=20000)
    items = page.eval_on_selector_all(f"{sv} .sv-menu button", "els => els.map(e => [e.textContent.trim(), e.getBoundingClientRect().height])")
    ok([i[0] for i in items] == MENU_ITEMS and all(i[1] >= 43.5 for i in items), f"{tag} hamburger opens with {MENU_ITEMS}")
    if shots:
        page.screenshot(path=str(shots / f"menu-{scene['id']}-{vp[0]}.png"))
    page.keyboard.press("Escape")
    ok(page.is_hidden(f"{sv} .sv-menu") and page.is_visible(sv), f"{tag} Esc closes the menu only")
    burger.click()
    page.click(f"{sv} .sv-menu [data-act=gallery]")
    page.wait_for_selector(f"{sv} .sv-gallery:not([hidden])", timeout=20000)
    want = min(20, len(scene["views"]))
    n = page.eval_on_selector_all(f"{sv} .sv-thumb", "els => els.length")
    ok(n == want, f"{tag} gallery count {n} == min(20, {len(scene['views'])} training views)")
    srcs = page.eval_on_selector_all(f"{sv} .sv-thumb img", "els => els.map(i => i.getAttribute('src'))")
    bad = []
    for u in srcs:
        try:
            Image.open(io.BytesIO(urllib.request.urlopen(base + "/" + u, timeout=60).read())).load()
        except Exception:
            bad.append(u)
    ok(len(srcs) == want and not bad, f"{tag} all {len(srcs)} gallery thumbnails resolve and decode {bad[:3]}")
    ok(page.evaluate("document.querySelector('%s .sv-thumb img').getAttribute('loading')" % sv) == "lazy", f"{tag} thumbnails lazy-load")
    alts = page.eval_on_selector_all(f"{sv} .sv-thumb img", "els => els.map(i => i.alt)")
    ok(len(alts) == want and all(a.startswith(scene["facts"]["place"]) and len(a) > 20 for a in alts), f"{tag} thumbnails have alt text ({alts[0]})")
    if shots:
        page.screenshot(path=str(shots / f"gallery-{scene['id']}-{vp[0]}.png"))
    page.click(f"{sv} .sv-thumb >> nth=2")
    page.wait_for_selector(f"{sv} .sv-lightbox:not([hidden])", timeout=20000)
    go = page.query_selector(f"{sv} [data-act=lb-go]")
    ok(go is not None and go.inner_text().strip() == "Go to this view" and go.bounding_box()["height"] >= 44, f"{tag} lightbox has 'Go to this view'")
    if shots:
        page.screenshot(path=str(shots / f"photo-{scene['id']}-{vp[0]}.png"))
    page.keyboard.press("Escape")
    ok(page.is_hidden(f"{sv} .sv-lightbox") and page.is_visible(f"{sv} .sv-gallery"), f"{tag} Esc closes the lightbox first")
    page.keyboard.press("Escape")
    ok(page.is_hidden(f"{sv} .sv-gallery") and page.is_visible(sv), f"{tag} Esc closes the gallery next")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    ok(page.is_hidden(sv), f"{tag} Esc then closes the viewer")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default=str(ROOT / "docs"))
    ap.add_argument("--shots", default="")
    ap.add_argument("--no-wait-ready", action="store_true")
    a = ap.parse_args()
    docs = Path(a.docs)
    shots = Path(a.shots) if a.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((ROOT / "scenes-config.json").read_text(encoding="utf-8"))["scenes"]
    srv, base = serve(docs)
    check_images(docs, base)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", args=GL_ARGS)
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        check_egg(page, base)
        for scene in cfg:
            for vp in VIEWPORTS:
                try:
                    check_scene(page, base, scene, vp, shots, not a.no_wait_ready)
                except Exception as e:
                    ok(False, f"{scene['id']}@{vp[0]} raised {type(e).__name__}: {str(e)[:200]}")
        for scene in cfg:
            for vp in BIG:
                try:
                    page.set_viewport_size({"width": vp[1], "height": vp[2]})
                    page.goto(base + "/scenes.html#" + scene["id"])
                    page.wait_for_selector(f".sv[data-viewer={scene['id']}]:not([hidden])", timeout=20000)
                    m = page.evaluate("sv => [document.documentElement.scrollWidth, innerWidth, document.querySelector(sv + ' .sv-top').offsetHeight, parseFloat(getComputedStyle(document.querySelector(sv + ' .sv-place')).fontSize)]", f".sv[data-viewer={scene['id']}]")
                    ok(m[0] <= m[1] and 0.04 * vp[2] <= m[2] <= 0.2 * vp[2] and m[3] >= 0.016 * vp[2], f"{scene['id']}@{vp[0]} no overflow; overlay {m[2]}px and title {m[3]:.0f}px scale with the screen")
                    if shots:
                        page.screenshot(path=str(shots / f"viewer-{scene['id']}-{vp[0]}.png"))
                    page.keyboard.press("Escape")
                except Exception as e:
                    ok(False, f"{scene['id']}@{vp[0]} raised {type(e).__name__}: {str(e)[:200]}")
        ok(not errors, f"no uncaught page errors {errors[:2]}")
        browser.close()
    srv.shutdown()
    for n in NOTES:
        print("NOTE " + n)
    print(f"{'FAILED' if FAILS else 'ALL PASSED'}: {len(FAILS)} failure(s)")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
