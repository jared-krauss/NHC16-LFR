# Markup contract (builders must follow; the checks select on exactly this)

Owner: checks-writer. Builders may not edit `checks/` or `tests/fixtures/`.

Change 2026-11-11 (Media/Bibliography restructure, edited by the site builder as checks owner for this change): sections are Home, Media, Bibliography, Slideshow; the old charts/posters/handouts/documents/news pages are gone (meta-refresh stubs only, config `redirects`). Card `data-kind` gains `figure`. B18 = Media page (was Charts), B19 = figure viewer (was Posters), `DATA` routes into the Bibliography. Fixtures set `figures_config`, `scene_facts_path`, `citations_path` and `thumbs_index` to empty, so fixture Media is the empty state; figures and the viewer are exercised on `--fixture real`.

## Page shell (every page)
- `<a class="skip-link" href="#main">` is the first focusable element; `<main id="main">`.
- `header`, `nav[aria-label]` (the section links, config order, labels from config), `main`, `footer`.
- Nav links: `nav a`, current page has `aria-current="page"` plus a non-colour cue (weight, underline or border).
- Footer holds `a.egg` (href -> `scenes.html`), 44x44 hit area, NOT inside `nav`. On every page, scenes included.
- Exactly one `<h1>`; for non-index pages its text equals the nav/hidden label. No skipped heading levels.
- Every `<img>` has `width`, `height` and (except the very first slide image) `loading="lazy"`.

## Link kinds (inside `main`; every `main a[href]` carries one)
- `a[data-link=page]` on-site page; `a[data-link=file]` a hosted file/download (text states "PDF" and size, e.g. "PDF, 0.2 MB" / "15.4 KB");
  `a[data-link=external]` another host: `rel` contains `noopener`, text or `aria-label` contains "opens" or "external", e.g. "Opens Fixture Gazette".
- The three kinds must have visibly different non-colour cues (icon/svg, `::before`/`::after` content, or distinct text marker).
- No link text "click here", "read more", "here", "more".

## Cards (one pattern for every item type)
```html
<article class="card" data-kind="chart|poster|pdf|link|news|figure|section|empty">
  <h3 class="card-title">..</h3>              <!-- non-empty; level follows page headings -->
  <p class="card-meta">
    <span class="source">outlet/source</span>  <!-- non-empty -->
    <span class="date">12 Mar 2017</span>       <!-- "D Mon YYYY" or exactly "Undated" -->
    <span class="card-kind">News</span>         <!-- type badge -->
  </p>
  ..links / image..
</article>
```
Order inside a card is fixed: `.card-title`, then `.card-meta` with `.source`, `.date`, `.card-kind` in that order.
- `data-kind=section` (index cards): needs `.card-title` and a count or "On its way"; source/date not required.
- Empty state: `<article class="card card--empty" data-kind="empty">` with a `.card-title` (section label or item title) and
  an element whose whole text is exactly `On its way` (class `card-empty-text`). Dashed border, no spinner, no red.
- A card with nothing hosted and no URL shows the text `Printed copy at the talk`.
- Hosted images: `<img alt="non-empty">` inside `a[data-link=file]` to the full-size image (Media figures state the size in the link's `aria-label`).
- Meta text (`.card-meta`, `.card-kind`, `small`, `footer *`, `.slide-counter`) may be 13-15px; everything else >= 16px.

## Media (`media.html`)
- Figure cards: `<article class="card fig-card" id="fig-N" data-kind="figure">`; `.card-title` starts with a `.fig-label` "Fig. N" then the title; `.card-meta .source` reads "Source: <a data-link=page href="bibliography.html#<source_id>">title, p. N</a>"; `.date` is the source's date; badge Illustration or Chart.
- Image: `a.fig-image[data-link=file]` -> full-size PNG, containing a webp `<img>` (non-empty alt, width/height, srcset with sizes). JS (`assets/media.js`) opens a `.viewer[role=dialog]`: dark backdrop, image fitted to the stage, wheel/pinch/drag zoom, buttons >= 44px (prev, next, zoom out/in, Fit, Close), Esc closes, no pushState. Without JS the link opens the PNG.
- Numbers come only from `figures-config.json` (`n`); never printed from the source document's own numbering.
- Charts: no Plotly on this page; a chart card (unnumbered, from charts_ready) has a static `<img>` and `a[data-link=page]` to `charts/<id>.html`; that page keeps `.js-plotly-plot` (`scrollZoom:false, displayModeBar:false, responsive:true`) and `.chart-source`. Charts still being tweaked: one `.media-note` line ("More charts on their way"), not cards.

## Bibliography (`bibliography.html`)
- Groups: `section.bib-group#<group id>` with an `h2`; entries `article.card.bib-entry#<source id>` (`data-kind` pdf|link) with `.bib-thumb` (image or typographic `.bib-tile`), `h3.card-title` (title, links to the document), `.card-meta` (`.source` = `strong.bib-author` + `.bib-pub`, `.date`, `.card-kind`), `p.bib-cite` MLA text (`small`, URLs plain text), optional Fig. cross-links, `.card-actions`.
- One title per document across Media, Bibliography and Slideshow (`title-overrides.json` by file name or URL, else the MLA record's title).

## Slideshow (`slideshow.html`)
```
#slideshow
  .slide-stage                       touch-action: pan-y
  button[data-action=pause]          first focusable inside #slideshow; text flips Pause <-> Play
  button[data-action=prev] / [data-action=next]   >= 44px
  button[data-action=fullscreen]
  [data-action=exit]                 link or button; returns to the page you came from
  .slide-counter                     "n / N"
```
- Adaptive layout (B27-B33): the visible slide's title/caption is `.slide-title` (or `figcaption`/`.slide-caption`); slide `img` uses `object-fit: contain`; card grids use `auto-fill`.
- Keys: ArrowLeft/Right, Home/End, Space (pause/play), Esc (exit). History: `replaceState` only, never `pushState`; no `unload`/`beforeunload` listeners.
- `?auto=0` or `prefers-reduced-motion: reduce` starts paused. Hover/focus inside stops auto-advance; a manual pause is never undone by itself.
- Without JS: a plain `ul`/`ol` list of the items inside `#slideshow` (or `main`). No items: one `.card--empty`.

## Scenes (`scenes.html`, hidden)
- B20 is retired in `run_checks.py` (records MANUAL): the scenes page, full-screen viewer and footer egg (`a.egg` -> `scenes.html#stratford`) are covered by `checks/check_scenes.py`. The old in-card DOM below is superseded; B21 still checks the egg is in every footer, >= 44px, focusable, not in nav.

- `<meta name="robots" content="noindex">`; not in any nav; plain `a` to `index.html` (Home).
- Each scene `[data-scene="<id>"]` (`walworth`, `stratford`) with `button[data-action=load]` whose text includes the size in MB ("Load 3D scene (9.0 MB)"),
  `[data-action=reset]` (>= 44px once loaded), a progress element (`progress`, `[role=progressbar]` or `.scene-progress`) while loading.
- `<canvas>` (created on load) has `aria-label` or `role=img` with a name; height <= 70% of viewport. One scene loaded at a time (<= 1 canvas).
- No `.sog` request before a tap. WebGL/load failure and no-JS show a plain message (no still images).

## QR
- `qr.png` (>= 1000 px wide, quiet zone >= 4 modules, dark on light, ECC M) and `qr.svg`; decodes to `site.public_url` exactly; URL printed as text on the index page.

## Selections schema: `schema/selections.schema.json` is the source of truth for all field names.
- Fixture notes: whole_files document A carries extra keys (`outlet`, `date`, `pages`) to prove they are tolerated; selections-half.json holds deliberately invalid items that the build must report ("invalid"/"skipped") and not crash on. No date key means "Undated"; whole_files source = host of `source_url` ("example.org"), else "Printed copy".
- Relative paths resolve against the project root. Path comparison with `licence_map` / `photos_cleared` is after normalising slashes and case.
- Config overlay: dicts deep-merge, lists (e.g. `splat_scenes`, `photos_cleared`) are replaced. The test overlay replaces `splat_scenes` with tiny fixture `.sog` files.
