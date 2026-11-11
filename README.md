# NHC16-LFR

Audience site for the talk "Live Facial Recognition at Notting Hill Carnival: The Met's First London Deployment, 2016"
(School of Architecture Research Conference, 12 Nov 2026). Live: https://jared-krauss.github.io/NHC16-LFR/
(the path is case-sensitive).

- `SPEC.md`: rules, architecture, the hand-off schema and the acceptance bar (B1-B33).
- `site-config.json`: sections, splat scenes, slideshow timings, photo and licence gates.
- `schema/selections.schema.json`: the hand-off file's field names.

## Rebuild and publish

```
D:\Dev\tools\.venv\Scripts\python.exe build.py
D:\Dev\tools\.venv\Scripts\python.exe checks\run_checks.py --fixture real --only B1,B12,B14,B26
git add docs && git commit -m "Rebuild from selections" && git push
```

GitHub Pages serves `docs/` on `main` and updates within about a minute.
