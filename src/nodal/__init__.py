"""Nodal: readable diagram DSL -> Scene IR -> SVG / APNG.

Pipeline (mirrors slidr):

    text --parse--> AST (model.Document)
         --style--> styled AST
         --layout + route (iterated until channels fit)--> laid-out AST
         --build--> Scene IR (ir.Scene)
         --writers--> render/svg.py, render/apng.py
"""
from __future__ import annotations

from pathlib import Path

from .ir import Scene
from .layout import layout
from .parser import NodalSyntaxError, parse, parse_file
from .render import write_apng, write_svg
from .route import Router
from .scene import SceneBuilder
from .style import apply_styles
from .theme import ThemeError, list_themes, theme_css

__all__ = ["render", "render_file", "build_scene", "scene_from_file", "parse", "parse_file",
           "write_svg", "write_apng", "Scene", "NodalSyntaxError", "ThemeError", "list_themes"]

MAX_PASSES = 4


def _style(doc, extra_css, theme):
    name = theme or doc.root.attrs.get("theme")
    if name:
        doc.stylesheets.insert(0, (theme_css(name, doc.base_dir), doc.base_dir))
    for css in extra_css or []:
        doc.stylesheets.append((css, doc.base_dir))
    apply_styles(doc)
    return doc


def _layout_and_route(doc) -> Router:
    """Lay out, route; if a channel between two ranks is too narrow for its lanes,
    widen exactly that gap and lay out again."""
    router = None
    for _ in range(MAX_PASSES):
        layout(doc)
        router = Router(doc).route()
        if not router.needs:
            break
        for (gid, rank), need in router.needs.items():
            g = doc.root if gid == doc.root.id else doc.items[gid]
            extra = getattr(g, "extra_gap", {})
            extra[rank] = extra.get(rank, 0.0) + need
            g.extra_gap = extra
    return router


def build_scene(doc, extra_css: list[str] | None = None, theme: str | None = None) -> Scene:
    """Style, then iterate layout -> route -> scene until edges clear the group titles
    (a crossed title that cannot slide asks for a wider group)."""
    _style(doc, extra_css, theme)
    scene = None
    for _ in range(MAX_PASSES):
        router = _layout_and_route(doc)
        builder = SceneBuilder(doc, router)
        scene = builder.build()
        if not builder.title_needs:
            break
        for gid, need in builder.title_needs.items():
            g = doc.items[gid]
            g.extra_w = getattr(g, "extra_w", 0.0) + need
    return scene


def scene_from_file(path: str | Path, extra_css: list[str] | None = None, theme: str | None = None,
                    allow_outside: bool = False) -> Scene:
    return build_scene(parse_file(path, allow_outside), extra_css, theme)


def render(text: str, base_dir: str = ".", extra_css: list[str] | None = None, theme: str | None = None,
           t: float | None = None, allow_outside: bool = False) -> str:
    """SVG text. t=None: animated (SMIL) SVG; t=seconds: static frame at that time."""
    return write_svg(build_scene(parse(text, base_dir, allow_outside), extra_css, theme), t)


def render_file(path: str | Path, extra_css: list[str] | None = None, theme: str | None = None,
                t: float | None = None, allow_outside: bool = False) -> str:
    return write_svg(scene_from_file(path, extra_css, theme, allow_outside), t)
