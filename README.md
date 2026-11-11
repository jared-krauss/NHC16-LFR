# NHC16-LFR

Audience site for the talk "The London Met's First Live Facial Recognition Deployment: The Trial at Notting Hill Carnival, 2016"
(School of Architecture Research Conference, 12 Nov 2026). Live: https://jared-krauss.github.io/NHC16-LFR/
(the path is case-sensitive).

- `SPEC.md`: rules, architecture, the hand-off schema and the acceptance bar (B1-B33).
- `site-config.json`: sections (Home, Paper, Media, Bibliography, Slideshow), redirects from retired pages, splat scenes, slideshow timings, photo and licence gates, bibliography groups.
- `figures-config.json`: the numbered figures (Fig. N) shown on Media and in the Slideshow; `title-overrides.json`: one display title per document (file name or URL -> title).
- `schema/selections.schema.json`: the hand-off file's field names.

## Updating the paper

- Edit `paper\paper.md` (plain text: a blank line between paragraphs, `#` for the title, `##` for section headings). "Fig. 3", "Figure 3" and "Figs. 2-3" become tappable and open that figure on the Paper page.
- Then run the two commands under "Rebuild and publish" below; the build prints a warning for any figure number that is not in `figures-config.json`.
- To try a different file without touching the real one, set `NHC_PAPER_SOURCE` to its path before building.

## Rebuild and publish

```
D:\Dev\tools\.venv\Scripts\python.exe build.py
D:\Dev\tools\.venv\Scripts\python.exe checks\run_checks.py --fixture real --only B1,B12,B14,B26
git add docs && git commit -m "Rebuild from selections" && git push
```

GitHub Pages serves `docs/` on `main` and updates within about a minute.
