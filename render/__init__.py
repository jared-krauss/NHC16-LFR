"""Page registry: section slug -> render module. Each module exposes render(ctx) -> Page."""
import importlib
from dataclasses import dataclass


@dataclass
class Page:
    slug: str
    title: str
    h1: str
    body_html: str
    head_extra: str = ""
    scripts_extra: str = ""
    in_nav: bool = True
    noindex: bool = False


def load(slug):
    """Return the render module for a slug, or None when there is none."""
    try:
        return importlib.import_module("render." + slug)
    except ModuleNotFoundError as e:
        if e.name == "render." + slug:
            return None
        raise
