# NHC16-LFR

Audience site for the talk "The London Met's First Live Facial Recognition Deployment: The Trial at Notting Hill Carnival, 2016"
(School of Architecture Research Conference, 12 Nov 2026). Live: https://jared-krauss.github.io/NHC16-LFR/
(the path is case-sensitive).

- `SPEC.md`: rules, architecture, the hand-off schema and the acceptance bar (B1-B33).
- `site-config.json`: sections (Home, Paper, Media, Bibliography, Slideshow), redirects from retired pages, splat scenes, slideshow timings, photo and licence gates, bibliography groups.
- `figures-config.json`: the numbered figures (Fig. N) shown on Media and in the Slideshow; `title-overrides.json`: one display title per document (file name or URL -> title).
- `schema/selections.schema.json`: the hand-off file's field names.

## Updating the paper

- Write on the Command Centre page **PhD > Writing room > Conference paper** (it autosaves).
- To put it on the site: double-click `publish-paper.bat` here. It copies the page text into `paper\paper.md` (title line, then your text), rebuilds `docs\`, commits and pushes. `--dry-run` (run `tools\publish_paper.py --dry-run`) shows what would change without touching anything.
- `paper\paper.md` is plain text: a blank line between paragraphs, `#` and `##` for headings. "Fig. 3", "Figure 3" and "Figs. 2-3" become tappable and open that figure on the Paper page; the build warns about a figure number not in `figures-config.json`.
- To try a different file without touching the real one, set `NHC_PAPER_SOURCE` to its path before building.

## Rebuild and publish

```
D:\Dev\tools\.venv\Scripts\python.exe build.py
D:\Dev\tools\.venv\Scripts\python.exe checks\run_checks.py --fixture real --only B1,B12,B14,B26
git add docs && git commit -m "Rebuild from selections" && git push
```

GitHub Pages serves `docs/` on `main` and updates within about a minute.
