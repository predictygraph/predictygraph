"""Scene IR: a laid-out, routed, fully styled diagram, independent of output format.

Pipeline (same shape as slidr):  .nod text → AST (model.Document) → layout + routing
→ Scene IR (this module) → output handlers (render/svg.py, render/apng.py, ...).

Everything a writer needs is resolved here: absolute geometry, paint, text lines and
animation tracks. Writers never look at the AST and never do layout or routing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .anim import Track

# Path segments: ("M", x, y) | ("L", x, y) | ("Q", cx, cy, x, y) | ("C", c1x, c1y, c2x, c2y, x, y)
Seg = tuple


@dataclass
class Elem:
    """One drawable (or a container of drawables).

    kind   group | rect | ellipse | circle | polygon | polyline | line | path | text | image
    geom   kind-specific geometry, e.g. rect {x,y,w,h,rx}, path {segs}, text {x,y,text,anchor}
    paint  presentation properties (fill, stroke, stroke-width, stroke-dasharray, opacity,
           font-family, ...). filter="shadow" refers to a scene-level effect.
    tracks animation tracks; the first keyframe equals the static value.
    """
    kind: str
    id: str = ""
    cls: str = ""
    geom: dict = field(default_factory=dict)
    paint: dict = field(default_factory=dict)
    tracks: list[Track] = field(default_factory=list)
    children: list["Elem"] = field(default_factory=list)

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


@dataclass
class Scene:
    width: float
    height: float
    background: str | None = None
    layers: list[Elem] = field(default_factory=list)  # painter's order: groups, edges, nodes

    def walk(self):
        for e in self.layers:
            yield from e.walk()

    def durations(self) -> list[float]:
        return [t.dur for e in self.walk() for t in e.tracks]

    def effects(self) -> set[str]:
        return {e.paint["filter"] for e in self.walk() if e.paint.get("filter")}
