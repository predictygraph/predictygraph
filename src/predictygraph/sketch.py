# SPDX-FileCopyrightText: 2026 Reza Jelveh
#
# SPDX-License-Identifier: Apache-2.0

"""Hand-drawn look (draw.io ``sketch=1``) and hatch fills, as plain path geometry.

Sketch: every outline or edge is flattened to a polyline and redrawn as two
slightly wobbly bezier strokes, like draw.io's rough.js renderer. The wobble is
seeded from the element id, so the same diagram always draws the same way.
Hatch: diagonal lines clipped to a rectangle, computed here (no SVG patterns or
clip paths, so every renderer shows it the same).
"""

from __future__ import annotations

import math
import random
import zlib

from .ir import Elem

Pt = tuple[float, float]


def flatten(segs) -> list[list[Pt]]:
    """Path segments -> polylines (one per subpath). Curves are sampled, arcs become chords."""
    out: list[list[Pt]] = []
    cur: list[Pt] = []
    for s in segs:
        op = s[0]
        if op == "M":
            if len(cur) > 1:
                out.append(cur)
            cur = [(s[1], s[2])]
        elif op == "L" or op == "A":
            cur.append((s[-2], s[-1]))
        elif op in ("Q", "C"):
            p0, ctrl = cur[-1], [(s[i], s[i + 1]) for i in range(1, len(s), 2)]
            for k in range(1, 9):
                t = k / 8
                pts = [p0, *ctrl]
                while len(pts) > 1:  # de Casteljau
                    pts = [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for a, b in zip(pts, pts[1:])]
                cur.append(pts[0])
        elif op == "Z" and cur:
            cur.append(cur[0])
    if len(cur) > 1:
        out.append(cur)
    return out


def _simplify(poly: list[Pt]) -> list[Pt]:
    """Merge nearly straight points so a sampled curve wobbles as a few strokes, not many.
    A point is kept once the path turns more than ~15° there, so corners survive."""
    out = [poly[0]]
    for i in range(1, len(poly) - 1):
        a, b, c = out[-1], poly[i], poly[i + 1]
        h1 = math.atan2(b[1] - a[1], b[0] - a[0])
        h2 = math.atan2(c[1] - b[1], c[0] - b[0])
        turn = abs((h2 - h1 + math.pi) % (2 * math.pi) - math.pi)
        if turn > 0.26 or math.dist(a, b) > 160:
            out.append(b)
    out.append(poly[-1])
    return out


def rough_segs(polys: list[list[Pt]], rng: random.Random, roughness: float) -> list:
    """One wobbly pass: each straight run becomes a cubic with jittered ends and controls."""
    segs: list = []
    for poly in polys:
        poly = _simplify(poly)
        j = lambda r: rng.uniform(-r, r)  # noqa: E731
        x, y = poly[0]
        segs.append(("M", x + j(roughness * 0.6), y + j(roughness * 0.6)))
        for a, b in zip(poly, poly[1:]):
            L = math.dist(a, b)
            if L < 0.5:
                continue
            r = roughness * (1 + min(L, 300) / 150)  # long strokes bow a little more, like rough.js
            nx, ny = (a[1] - b[1]) / L, (b[0] - a[0]) / L  # unit normal
            c1, c2 = rng.uniform(-r, r), rng.uniform(-r, r)
            p1 = (a[0] + (b[0] - a[0]) * 0.35 + nx * c1, a[1] + (b[1] - a[1]) * 0.35 + ny * c1)
            p2 = (a[0] + (b[0] - a[0]) * 0.7 + nx * c2, a[1] + (b[1] - a[1]) * 0.7 + ny * c2)
            segs.append(("C", *p1, *p2, b[0] + j(r * 0.5), b[1] + j(r * 0.5)))
    return segs


def outline(el: Elem) -> list[list[Pt]] | None:
    """Closed outline polylines of a shape element (rect corners are kept square)."""
    g = el.geom
    if el.kind == "rect":
        x, y, w, h = g["x"], g["y"], g["w"], g["h"]
        return [[(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]]
    if el.kind == "polygon":
        pts = list(g["points"])
        return [pts + pts[:1]]
    if el.kind == "ellipse":
        n = 16
        return [
            [(g["cx"] + g["rx"] * math.cos(2 * math.pi * k / n), g["cy"] + g["ry"] * math.sin(2 * math.pi * k / n)) for k in range(n + 1)]
        ]
    if el.kind == "path":
        return flatten(g["segs"])
    return None


def sketchify(el: Elem, seed: str, roughness: float = 1.5) -> list[Elem]:
    """Replace a static element by its hand-drawn version: fill pass + two wobbly strokes.

    Animated elements and anything without an outline are returned unchanged."""
    polys = outline(el)
    if polys is None or el.tracks or roughness <= 0:
        return [el]
    rng = random.Random(zlib.crc32(seed.encode()))
    out = []
    fill = el.paint.get("fill", "none")
    stroke = el.paint.get("stroke", "none")
    if fill not in ("none", "transparent"):
        closed = [p for p in polys if math.dist(p[0], p[-1]) < 1]
        if closed:
            out.append(
                Elem("path", cls=el.cls, geom={"segs": rough_segs(closed, rng, roughness * 0.4)}, paint={**el.paint, "stroke": "none"})
            )
    if stroke != "none":
        line = {k: v for k, v in el.paint.items() if k not in ("fill", "filter")}
        line.update({"fill": "none", "stroke-linecap": "round", "stroke-linejoin": "round"})
        for _ in range(2):
            out.append(Elem("path", cls=el.cls, geom={"segs": rough_segs(polys, rng, roughness)}, paint=dict(line)))
    if el.paint.get("filter") and out:
        out[0].paint["filter"] = el.paint["filter"]
    return out or [el]


def hatch(x: float, y: float, w: float, h: float, color: str, gap: float = 8.0, width: float = 1.0) -> Elem:
    """45° lines (bottom-left to top-right) clipped to the rectangle."""
    segs = []
    gap = max(2.0, gap)
    c = gap / 2
    while c < w + h:  # the line where (px - x) + (py - y) = c, rising to the right on screen
        u0, u1 = max(0.0, c - h), min(c, w)
        segs += [("M", x + u0, y + c - u0), ("L", x + u1, y + c - u1)]
        c += gap
    return Elem("path", cls="pdg-hatch", geom={"segs": segs}, paint={"fill": "none", "stroke": color, "stroke-width": width})
