"""Nodal: readable diagram DSL -> static SVG."""
from __future__ import annotations

from pathlib import Path

from .layout import layout
from .parser import NodalSyntaxError, parse, parse_file
from .style import apply_styles
from .svg import loop_seconds, render_svg
from .theme import ThemeError, list_themes, theme_css

__all__ = ["render", "render_file", "parse", "parse_file", "NodalSyntaxError", "ThemeError", "list_themes"]


def _prepare(doc, extra_css, theme):
    name = theme or doc.root.attrs.get("theme")
    if name:
        # theme sits under the file's own stylesheets
        doc.stylesheets.insert(0, (theme_css(name, doc.base_dir), doc.base_dir))
    for css in extra_css or []:
        doc.stylesheets.append((css, doc.base_dir))
    apply_styles(doc)
    layout(doc)
    return doc


def render(text: str, base_dir: str = ".", extra_css: list[str] | None = None, theme: str | None = None,
           t: float | None = None) -> str:
    """SVG text. t=None: animated (SMIL) SVG; t=seconds: static frame at that time."""
    return render_svg(_prepare(parse(text, base_dir), extra_css, theme), t)


def render_file(path: str | Path, extra_css: list[str] | None = None, theme: str | None = None,
                t: float | None = None) -> str:
    return render_svg(_prepare(parse_file(path), extra_css, theme), t)


def load_file(path: str | Path, extra_css: list[str] | None = None, theme: str | None = None):
    """Parsed, styled and laid-out document (for frame export)."""
    return _prepare(parse_file(path), extra_css, theme)
