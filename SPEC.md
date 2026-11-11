# NHC16-LFR audience site: spec and bar

Audience site for a 20-minute talk, School of Architecture Research Conference, Thu 12 Nov 2026:
"Live Facial Recognition at Notting Hill Carnival: The Met's First London Deployment, 2016".
Live address (once approved): `https://jared-krauss.github.io/NHC16-LFR/` (GitHub Pages, serving `docs/` on `main`).

## Hard rules (every unit)
1. **No ghostwriting.** Builders write NO prose: no captions, descriptions, intros, summaries or opinions. Allowed text: section labels (plain nouns), the talk title/date/venue above, item titles, outlets, dates, sources, file type/size, licence lines, controls ("Pause", "Next", "Load 3D scene (9.0 MB)"), and the fixed empty-state text "On its way". Anything else comes verbatim from `selections.json` fields.
2. **Copyright.** Host a file (PDF, page image) only when its item carries a non-empty `licence_note`. Jared's decision (print-pack chat, 11 Nov): public documents incl. press/NEC/academic copies may be hosted "for the 2-day conference audience (personal research use)"; the print-pack session records that in `licence_note`. Hosted third-party files are to come down after the conference (follow-up filed at wrap). Everything else is a link to `source_url`, or, with no URL, a card saying "Printed copy at the talk". News and papers are always links.
3. **No local paths or personal data in output.** Nothing under `docs/` may contain `C:\`, `D:\`, `E:\`, `file:` or a Windows user name.
4. **Relative links only** (no leading `/`), so the site works at `/NHC16-LFR/` and from a local server.
5. **No web fonts, no CDNs, no trackers.** System font stack; all JS/CSS self-hosted.
6. Selections may be missing, empty or half-filled at any build; the build must never crash on that.
7. **Internal addresses never published.** `selections.json` `url`/`path` fields may be Command Centre, Tailscale or local addresses. Use them only to find source files at build time; never write them into `docs/`.
8. **People in photos.** A photo from `selections.photos` is published only if its path is listed in `site-config.json` `photos_cleared` (Jared clears each one). Uncleared photos are skipped silently in the build (logged to the build's stdout).
9. **Walworth renders are not public.** Splat stills from `E:\Splat-Sync\...\renders\` are Anthropic-only; never copy them into `docs/`. Splat fallbacks are a plain message.

### selections.json schema (CANONICAL, from the plan doc; written only by the print-pack session)
```json
{
  "updated": "ISO time",
  "whole_files": [{"title": "", "path": "", "use": "print|host|link", "licence_note": "", "source_url": ""}],
  "posters_a3": [{"title": "", "source_path": "", "page": 0, "why": "his words if he gave any"}],
  "charts_ready": [{"id": "dv-038", "url": ""}],
  "charts_tweak": [{"id": "", "url": "", "tweaks": ""}],
  "news": [{"title": "", "outlet": "", "date": "", "url": "", "kind": "news|commentary"}],
  "photos": [{"path": "", "caption": ""}],
  "splats": [{"title": "", "url_or_path": ""}]
}
```
Readers must tolerate extra keys (the print-pack session may add e.g. `outlet`, `date`, `pages` to `whole_files`) and missing keys. `whole_files` has no date by default: show a date only if a `date` key exists, else "Undated". `photos[].caption` and `posters_a3[].why` are Jared's words: shown verbatim, or nothing. Source for a `whole_files` card = the host of `source_url` (e.g. "met.police.uk"), else "Printed copy".

### Where each data kind really comes from
- **Licence lookup** (posters, handouts, documents): an item may be hosted if (a) it has its own non-empty `licence_note`, or (b) its source path matches a `whole_files` row whose `licence_note` is non-empty, or (c) its source path is a key in `site-config.json` `licence_map` (owner: orchestrator; facts only). Otherwise link/"Printed copy at the talk".
- **Posters:** `posters_a3[]` = `{title, source_path, page, why}`. Page images already rendered by the print-pack session exist as PNGs in `E:\Outputs\phd-conference-2026-11-12\_work\posters\` and final A3 PDFs in `...\print-ready\posters-a3\`. Use an existing PNG if one matches (`candidates.json` there maps them); otherwise render the page with `pypdf`+Playwright or skip with "Printed copy at the talk". `fitz` is NOT installed; do not add it. `why` is NEVER displayed (orchestrator decision 11 Nov: it records why he picked it and held internal notes).
- **Charts:** `charts_ready[]`/`charts_tweak[]` = `{id, url[, tweaks]}`. Resolve `id` (e.g. `dv-038`) against `D:\Dev\tools\dashboard\dataviz-gallery\` (`dv-NNN.html`, `thumbs\`, shared `alhfrs-data.js` 1.9 MB + `alhfrs-chartkit.js`). Prior art for a self-contained public chart page: `D:\Dev\_analysis\gallery-embed-2026-11\` (`SPIKE-2-standalone.md`, `DECISION.md`, `standalone-test\dv-003.inline.standalone.html`, `libs\plotly-2.35.2.min.js`). Title and data source line come from the chart file itself (facts), never written by the builder.
- **Slideshow list:** `site-config.json` `slideshow.items` (owner: orchestrator; Jared's choices, ordered list of `{kind: chart|poster|photo|news_image|video, ref}`). If empty, derive: `charts_ready` + licensed `posters_a3` + cleared `photos` + `splats` entries that are video files. Video slides are optional (none exist yet).

## Architecture (the interface; agreed before building)

```
NHC16-LFR/
  site-config.json        # sections, labels, order, paths, splat scenes, slideshow timings  (owner: shell/integration)
  build.py                # python build.py [--selections PATH] [--config-overlay PATH] [--out docs]  (owner: shell/integration)
                          # exit 0 on success; prints one line per skipped item and why
  render/__init__.py      # registry: section slug -> module                                   (owner: shell/integration)
  render/common.py        # shared helpers: esc(), card(), empty_state(), file_size(), link kinds (owner: shell)
  render/<slug>.py        # one module per page, each exposes render(ctx) -> Page             (owner: its unit)
  templates/base.html     # page shell: skip link, header, nav, main, footer                   (owner: shell)
  assets/site.css         # tokens + layout + card + empty state                               (owner: shell)
  assets/site.js          # tiny, optional                                                    (owner: shell)
  assets/<unit>.css|.js   # unit-specific                                                      (owner: that unit)
  vendor/                 # third-party (playcanvas, plotly) with licence files                (owner: the unit that needs it)
  tests/fixtures/         # selections-empty.json, -half.json, -full.json + tiny sample assets (owner: shell)
  checks/                 # acceptance checks. BUILDERS MAY NOT EDIT.                         (owner: checks-writer)
  docs/                   # BUILD OUTPUT, published. Never hand-edited.
```

`render(ctx)` gets `ctx = {"config": dict, "sel": dict (normalised selections, every key present as a list), "out": Path (docs/), "copy_asset": fn(src_path, dest_rel) -> rel_url}` and returns
`Page(slug, title, h1, body_html, head_extra="", scripts_extra="", in_nav=True, noindex=False)`.
`build.py` wraps body_html in `templates/base.html`, writes `docs/<slug>.html` (home = `docs/index.html`), copies `assets/`, writes `docs/qr.svg` + `docs/qr.png`, and `docs/.nojekyll`.

### Pages and their data
| slug | nav label | data from selections.json | shows |
|---|---|---|---|
| index | Home | all | talk title, date, venue; a card per section with item count or "On its way"; QR + URL ("Share this site") |
| charts | Charts | `charts_ready` (shown), `charts_tweak` (shown as "On its way" with title) | static image per chart, tap -> interactive chart page on-site |
| posters | Posters | `posters_a3` | page image (if licensed) -> full-size, pinch-zoomable; else "Printed copy at the talk" |
| handouts | Handouts | `whole_files` with `use=print` | hosted PDF link with "PDF, x.x MB" if licensed, else source link / "Printed copy at the talk" |
| documents | Documents | `whole_files` with `use=host` or `use=link` | hosted PDF (licensed) or external link |
| news | News | `news` | title, outlet, date, kind (news/commentary); external link |
| slideshow | Slideshow | `site-config.json` `slideshow.items`, else derived (see below) | auto-advancing presentation mode |
| scenes | (not in nav) | config `splat_scenes` + `selections.splats` | easter egg: two 3D splat scenes, load on tap |

Splat scenes (Jared's picks, 11 Nov): Walworth `2026-10-26_r3v9c-solve_15k-steps_best-longer-training_seed42.sog` (9.0 MiB), Stratford `2026-10-23_S41_3k-steps_full-res_seed7.sog` (3.7 MiB); sources in `D:\Dev\tools\dashboard\splat-ranking-data\`. Viewer: PlayCanvas 2.23.3 (MIT), `.sog` only.

## The bar (merged from three bar scouts, 11 Nov; each item is a pass/fail check)
Scouts answered from established standards without live searches; numbers are the standard WCAG 2.2 / NN/g / HIG ones.

**Navigation and access**
- B1 Reflow: at 375x812 and at 320 wide, `scrollWidth <= clientWidth` on every page (WCAG 1.4.10). No `user-scalable=no` / `maximum-scale`.
- B2 Every page reachable in <= 2 taps from the QR landing page; every nav page in 1 tap from every other nav page. All section links visible on load at 375x812, no hamburger (NN/g hidden-nav).
- B3 Back always works: plain `<a href>` page links; 3 page hops then 3 Back presses return in order; slideshow uses `replaceState` only, so ONE Back leaves it; no `unload` handlers (bfcache).
- B4 Where am I: current nav link has `aria-current="page"` and a non-colour cue; `<h1>` matches the nav label.
- B5 Skip link is the first focusable element, visible on focus, targets `<main id="main">`.
- B6 Landmarks/headings: one `<h1>`, no skipped heading levels, `header`, `nav[aria-label]`, `main`, `footer`. axe-core: zero serious/critical violations.
- B7 Focus visible on every link/button (no bare `outline:none`), not hidden under sticky elements.
- B8 Touch targets: nav, controls and card links >= 44x44 CSS px; nothing interactive < 24x24 (WCAG 2.5.8).
- B9 Link text makes sense alone; no "click here"/"read more"; PDF links state "PDF" and size; external links say "opens <outlet/site>" in text or accessible name and use `rel="noopener"`.
- B10 Contrast >= 4.5:1 body, >= 3:1 large text and UI; empty-state text also >= 4.5:1.

**Information design**
- B11 Body text >= 16px; metadata >= 13px; line-height 1.4-1.6 body; <= 4 font sizes; one font family (system stack), <= 2 weights.
- B12 One card pattern for every item type: same title + one metadata line (source/outlet, date, type badge) in the same order. Dates in one format ("12 Mar 2017"); missing date shows "Undated", never blank.
- B13 Three link kinds visibly distinct without colour: on-site page, external site, file download (icon or text cue).
- B14 Empty state: same card shape, dashed border, text "On its way", no dead link, no spinner, no error colour. No 404-able link anywhere (link checker over `docs/`).
- B15 Restraint: neutral background, one accent hue + greys, no emoji, no decorative imagery, no motion except the slideshow and loaders.
- B16 Page section labels are plain nouns, and the order of sections matches `site-config.json` (so print and site can share it).

**Interactivity**
- B17 Slideshow: visible Pause/Play first in tab order with label that flips; Prev/Next >= 44px; "n / total" counter; ArrowLeft/Right, Home/End, Space, Esc; swipe on touch with `touch-action: pan-y`; auto-rotation stops on focus/hover and does not resume by itself after a manual pause; dwell >= 6 s for images/charts, 10 s for text-heavy; video advances on `ended`, `muted playsinline`; `prefers-reduced-motion: reduce` starts paused; `?auto=0` starts paused; fullscreen button (Fullscreen API with a `100dvh` fixed-overlay fallback); Exit returns to the page you came from.
- B18 Charts: the charts page loads NO Plotly; static image + alt text per chart; the interactive chart page uses `scrollZoom:false`, `displayModeBar:false`, `responsive:true`, and a vertical swipe over the chart scrolls the page (dragmode false / fixedrange); data source line under every chart.
- B19 Posters/document images: thumbnail -> full-size image that can be pinch-zoomed; card states "A3 poster" / page number and file size.
- B20 Splat page: zero `.sog` bytes fetched before a tap; button states the size ("Load 3D scene (9.0 MB)"); progress shown during load; gesture hint; Reset view button >= 44px; WebGL-missing and load-failure fallbacks show a plain message (no still images: rule 9); canvas has an accessible name; canvas <= 70vh so the page can still be scrolled, or touch is captured only after an explicit "Enter 3D"; one scene loaded at a time; a normal link back to Home.
- B21 Easter egg: trigger is a real `<a>` reachable by Tab and tap, >= 44px hit area, subtle but present on every page (footer), not in nav, `noindex` on the scenes page.
- B22 QR: encodes exactly the approved URL; quiet zone >= 4 modules; dark on light; error correction M; URL shown as text next to it; decodes back to the URL with a script; PNG >= 1000 px for the slide.

**Weight and robustness**
- B23 Home: <= 150 KB total transfer (HTML+CSS+JS+QR, no web fonts); every nav page <= 1 MB before user interaction (images lazy-loaded, `width`/`height` set); Plotly and PlayCanvas load only on the pages that need them.
- B24 Works with JS off: every nav page shows its content (slideshow shows a plain list of its items; scenes page shows the fallback).
- B25 Build robustness: build succeeds and all checks pass with the empty, half and full fixtures and with selections.json absent; every section shows content or "On its way".
- B26 Hard rules 1-9 above hold (script: no local paths in `docs/`; no `ts.net`, `tailscale`, `localhost`, `127.0.0.1`, `100.` IP hosts, `:8787`/`:8788` ports in `docs/`; no external `src=`/`href=` to CDNs; hosted files only with a licence per the lookup; uncleared photos absent; no file from a `renders` folder).

**Adaptive layout (Jared, 11 Nov: "make sure the layout adapts to the screen size, so it's not fixed to phone width"; responsive bar scout, sources opened)**
Viewport matrix: 320x568, 375x667, 414x896, 768x1024, 1024x768, 812x375 (landscape phone), 1280x800, 1440x900, 1920x1080.
- B27 No horizontal overflow and no element with `getBoundingClientRect().right > innerWidth` on every page at every matrix size (slideshow stage and 3D canvas may be fixed-ratio but must still fit).
- B28 Spare width becomes more columns: on pages with >= 3 cards (full fixture), distinct card `left` values are 1 at 375, >= 2 at 768, >= 3 at 1280, >= 4 at 1920; grids use `auto-fill` (not `auto-fit`); no card wider than 2x the narrowest in the same grid.
- B29 Text measure: no paragraph or card-meta line in `main` wider than 45rem (~75ch) at 1920; content centred with fluid gutters >= 12 px at 320 and <= 64 px at 1920.
- B30 Fluid type: no `font-size` in `px` in site CSS (rem/em/clamp only); every `clamp()` font-size has rem bounds with max >= 1.25x min; body computed >= 16 px at 320; still no horizontal overflow at 200% text zoom (root font-size 200% at 1280 wide).
- B31 Header: at 1280 and wider, all 7 nav links share one row (same `offsetTop`); at 360 all visible, header <= 3 rows of links.
- B32 Images: every `img` has width/height attributes or CSS aspect-ratio; where `srcset` exists `sizes` exists and uses no `%`; at 375 wide no image's `naturalWidth` > 3x its CSS width; CLS <= 0.1 measured with a layout-shift PerformanceObserver on charts, posters, slideshow.
- B33 Slideshow at 1920x1080 and 812x375: image fully inside viewport with controls, `object-fit: contain`, rendered box aspect ratio within 1% of natural; at 1920x1080 slide caption/title computed font-size >= 28 px; no `100vh` without a `dvh`/`svh` line after it in any CSS.

## GitHub Pages constraints (checked 11 Nov)
- Pages works on this account (ALHFRS is live at jared-krauss.github.io/ALHFRS/, HTTPS enforced).
- **Project paths are case-sensitive**: `/ALHFRS/` = 200, `/alhfrs/` = 404. The QR and the printed URL must match the repo name's exact case.
- No `.mjs` files in `docs/`: vendored ES modules are copied as `.js` and their import specifiers rewritten, so MIME type is never a risk. `.sog` is fetched as binary (MIME irrelevant).
- `docs/.nojekyll` present (Jekyll would drop `_`-prefixed files). No file > 50 MB (largest planned: 9.0 MiB). Plain static files only; no server code.

## Environment facts (for every helper)
- Python: `D:\Dev\tools\.venv\Scripts\python.exe` (has `segno` 1.6.6, `playwright`, `PIL`, `pypdf`; NOT `fitz`).
- Playwright works ONLY with `p.chromium.launch(channel="msedge")`; bundled Chromium is not installed.
- axe-core is not installed: the checks-writer vendors `axe.min.js` into `checks/vendor/` (download one pinned version from cdnjs or jsdelivr; record version + licence).
- Serve `docs/` locally for checks with `python -m http.server <port> -d docs` on a free port (not 8787/8788).
- Shell: PowerShell. Windows paths. Write files as UTF-8 without BOM.

## Ownership of tests
`tests/fixtures/` and `checks/` belong to the checks-writer. Builders read them, never edit them. Fixtures: `selections-empty.json` (`{}`), `selections-half.json`, `selections-full.json` (includes: an item missing `licence_note`, an item missing a date, all three `use` values, a `charts_tweak` row, a news item of each kind, a photo NOT in `photos_cleared`), plus tiny sample assets they reference (under `tests/fixtures/assets/`). A matching `tests/fixtures/site-config.test.json` overlay may set `photos_cleared`/`licence_map` for fixture items.
