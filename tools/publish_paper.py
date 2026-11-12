"""Publish the conference paper written on the Command Centre page to the audience site.

    python tools/publish_paper.py [--dry-run]

Reads tools/dashboard/page-state/phd-conference-paper.json (field "text"), writes paper/paper.md as
"# <title>", a blank line, then the text (title only when the text is empty), rebuilds docs/, then commits and pushes.
--dry-run writes the file to a temp path, prints a diff summary and changes nothing else.
"""
import argparse
import difflib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = Path(r"D:\Dev\tools\dashboard\page-state\phd-conference-paper.json")
FIGS_COPY = Path(r"D:\Dev\tools\dashboard\phd-conference-paper-figures.json")
PAPER = ROOT / "paper" / "paper.md"
REQUIRED_PAGES = {"index.html", "paper.html", "bibliography.html"}
TITLE = "The London Met's First Live Facial Recognition Deployment: The Trial at Notting Hill Carnival, 2016"


def read_text():
    if not STATE.exists():
        return ""
    return (json.loads(STATE.read_text(encoding="utf-8-sig")).get("text") or "").replace("\r\n", "\n").strip()


def compose(text):
    return "# " + TITLE + "\n" + ("\n" + text + "\n" if text else "")


def sync_figures():
    cfg = json.loads((ROOT / "figures-config.json").read_text(encoding="utf-8"))
    rows = [{"n": f["n"], "title": f["title"]} for f in cfg["figures"]]
    FIGS_COPY.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run(cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    text = read_text()
    new = compose(text)
    old = PAPER.read_text(encoding="utf-8") if PAPER.exists() else ""
    words = len(text.split())
    if args.dry_run:
        out = Path(tempfile.gettempdir()) / "paper-dry-run.md"
        out.write_text(new, encoding="utf-8")
        diff = list(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0))
        added = sum(1 for d in diff if d.startswith("+") and not d.startswith("+++"))
        removed = sum(1 for d in diff if d.startswith("-") and not d.startswith("---"))
        print("Dry run: %d words from the page; would change paper.md by +%d/-%d lines. Draft written to %s. Nothing built, committed or pushed." % (words, added, removed, out))
        return 0
    if new == old:
        print("Nothing to publish: the page text matches paper.md already.")
        return 0
    before_pages = {p.name for p in (ROOT / "docs").glob("*.html")}
    PAPER.write_text(new, encoding="utf-8", newline="\n")
    sync_figures()
    b = run([sys.executable, "build.py"])
    if b.returncode:
        print(b.stdout[-1500:] + b.stderr[-1500:])
        PAPER.write_text(old, encoding="utf-8", newline="\n")
        print("FAILED: the build stopped, so nothing was published. paper.md was put back as it was; fix the problem above and run again.")
        return 1
    if b.stdout.strip():
        print(b.stdout.strip())
    missing = [n for n in sorted(before_pages | REQUIRED_PAGES) if not (ROOT / "docs" / n).is_file() or (ROOT / "docs" / n).stat().st_size < 1000]
    if missing:
        PAPER.write_text(old, encoding="utf-8", newline="\n")
        print("FAILED: docs/ is incomplete after the build (missing or empty: %s), so nothing was published. paper.md was put back as it was." % ", ".join(missing))
        return 1
    run(["git", "add", "paper", "docs"])
    c = run(["git", "commit", "-m", "Paper text update"])
    if c.returncode:
        print(c.stdout + c.stderr)
        print("FAILED: nothing new to commit, or the commit was refused.")
        return 1
    p = run(["git", "push"])
    if p.returncode:
        print(p.stderr)
        print("FAILED: committed on this PC but the push to GitHub failed. Run again once you are online.")
        return 1
    print("Published: %d words are on the audience site (live in about a minute)." % words)
    return 0


if __name__ == "__main__":
    sys.exit(main())
