"""Nodal: readable diagram DSL -> static SVG."""
from __future__ import annotations

from pathlib import Path

from .layout import layout
from .parser import NodalSyntaxError, parse, parse_file
from .style import apply_styles
from .svg import render_svg

__all__ = ["render", "render_file", "parse", "parse_file", "NodalSyntaxError"]


def _finish(doc, extra_css):
    for css in extra_css or []:
        doc.stylesheets.append((css, doc.base_dir))
    apply_styles(doc)
    layout(doc)
    return render_svg(doc)


def render(text: str, base_dir: str = ".", extra_css: list[str] | None = None) -> str:
    return _finish(parse(text, base_dir), extra_css)


def render_file(path: str | Path, extra_css: list[str] | None = None) -> str:
    return _finish(parse_file(path), extra_css)
