"""Document model: graph, groups, nodes, edges."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Item:
    id: str
    label: str | None = None
    classes: list[str] = field(default_factory=list)
    attrs: dict[str, str] = field(default_factory=dict)
    parent: "Group | None" = None
    style: dict[str, str] = field(default_factory=dict)
    # layout results (relative to parent content origin, then absolute)
    w: float = 0.0
    h: float = 0.0
    x: float = 0.0
    y: float = 0.0
    ax: float = 0.0
    ay: float = 0.0
    kind: str = "node"

    @property
    def cx(self) -> float:
        return self.ax + self.w / 2

    @property
    def cy(self) -> float:
        return self.ay + self.h / 2

    def ancestors(self) -> list["Group"]:
        out, p = [], self.parent
        while p is not None:
            out.append(p)
            p = p.parent
        return out


@dataclass
class Node(Item):
    implicit: bool = False
    image: dict | None = None
    text_lines: list[str] = field(default_factory=list)
    text_w: float = 0.0
    text_h: float = 0.0


@dataclass
class Group(Item):
    kind: str = "group"
    children: list[Item] = field(default_factory=list)
    defaults: dict[str, dict[str, str]] = field(default_factory=dict)
    # content box offset inside the group box
    ox: float = 0.0
    oy: float = 0.0
    label_h: float = 0.0


@dataclass
class Edge:
    src: str
    dst: str
    arrow: str  # none|end|start|both
    body: str  # solid|thick|dashed
    label: str | None = None
    classes: list[str] = field(default_factory=list)
    attrs: dict[str, str] = field(default_factory=dict)
    scope: Group | None = None
    style: dict[str, str] = field(default_factory=dict)
    label_style: dict[str, str] = field(default_factory=dict)
    index: int = 0
    waypoints: list[tuple[float, float]] = field(default_factory=list)
    wp_owner: Group | None = None
    dir_hint: str | None = None
    kind: str = "edge"
    id: str = ""


@dataclass
class Document:
    root: Group
    edges: list[Edge] = field(default_factory=list)
    stylesheets: list[tuple[str, str]] = field(default_factory=list)  # (css text, base dir)
    items: dict[str, Item] = field(default_factory=dict)
    base_dir: str = "."
    allow_outside: bool = False  # let image=/css "..." read files outside base_dir

    def walk(self, g: Group | None = None):
        g = g or self.root
        for c in g.children:
            yield c
            if isinstance(c, Group):
                yield from self.walk(c)
