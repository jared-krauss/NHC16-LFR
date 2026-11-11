"""Regenerates the tiny fixture assets under tests/fixtures/assets/.

Run: D:\\Dev\\tools\\.venv\\Scripts\\python.exe tests\\fixtures\\make_assets.py
Everything produced is clearly labelled as a fixture. Deterministic bytes.
"""
import random
from pathlib import Path

from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter

A = Path(__file__).resolve().parent / "assets"
(A / "renders").mkdir(parents=True, exist_ok=True)


def page_image(label, size=(595, 842), colour=(235, 235, 235)):
    im = Image.new("RGB", size, colour)
    d = ImageDraw.Draw(im)
    d.rectangle([20, 20, size[0] - 20, size[1] - 20], outline=(60, 60, 60), width=4)
    d.text((40, 60), label, fill=(0, 0, 0))
    d.text((40, 90), "FIXTURE - not real content", fill=(0, 0, 0))
    return im


def make_pdf(name, title):
    tmp = A / ("_tmp_" + name)
    page_image(title).save(tmp, "PDF", resolution=72.0)
    r = PdfReader(str(tmp))
    w = PdfWriter()
    w.add_page(r.pages[0])
    w.add_metadata({"/Title": title})
    with open(A / name, "wb") as f:
        w.write(f)
    tmp.unlink()


make_pdf("doc-licensed-print.pdf", "Fixture document A")
make_pdf("doc-unlicensed.pdf", "Fixture document B (no licence)")
make_pdf("doc-licence-map.pdf", "Fixture document C")
make_pdf("poster-licensed.pdf", "Fixture poster A")
make_pdf("poster-unlicensed.pdf", "Fixture poster B (no licence)")

page_image("Fixture photo (cleared)", (400, 300), (210, 225, 240)).save(A / "photo-cleared.png")
page_image("Fixture photo (NOT cleared)", (400, 300), (240, 215, 215)).save(A / "photo-uncleared.png")
page_image("Fixture render (must never be published)", (400, 300), (215, 240, 215)).save(
    A / "renders" / "walworth-still.png"
)

rng = random.Random(16)
(A / "scene-walworth.sog").write_bytes(bytes(rng.getrandbits(8) for _ in range(180_000)))
(A / "scene-stratford.sog").write_bytes(bytes(rng.getrandbits(8) for _ in range(90_000)))
print("fixture assets written to", A)
