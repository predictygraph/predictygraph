# SPDX-FileCopyrightText: 2026 Reza Jelveh
#
# SPDX-License-Identifier: Apache-2.0

"""AST + layout + routing -> Scene IR.

Also owns the decisions that need the routed geometry of everything at once:
* group titles slide along their top edge to a span no edge crosses; if no span is
  wide enough the title is lifted above the edges on a patch of the group's fill, so
  the crossing line stops around the text (plain geometry: works in every renderer);
* edge labels sit on the longest straight run of their own edge.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

from .anim import BORDER_MODES, border_tracks, dash_len, draw_tracks, flow_tracks, seconds
from .ir import Elem, Scene
from .layout import SUB_GAP
from .model import Document, Edge, Group, Node
from .route import Diagonal, Router, flow_dir, lca
from .style import box4, px
from .styleutil import LINE_H, accent, font_size, has_title_band, node_padding, text_block, title_position

TITLE_PAD = 6.0
ER_HEADS = ("one", "many", "zero-one", "zero-many", "one-many")


def point_along(poly: list[tuple[float, float]], frac: float) -> tuple[float, float]:
    """The point `frac` (0..1) of the way along a polyline, by length."""
    lens = [math.dist(a, b) for a, b in zip(poly, poly[1:])]
    goal, acc = sum(lens) * frac, 0.0
    for (a, b), seg in zip(zip(poly, poly[1:]), lens):
        if seg and acc + seg >= goal:
            t = (goal - acc) / seg
            return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        acc += seg
    return poly[-1]


def corner_radius(st: dict, shape: str, w: float, h: float) -> float:
    """The corner radius a box shape is drawn with (shared by the box and its accent bar)."""
    if shape == "pill":
        return h / 2
    r = px(st.get("border-radius"), 0)
    return max(r, 10) if shape == "round" else r


def accent_segs(x: float, y: float, w: float, h: float, bw: float, r: float, side: str) -> list:
    """Path for a `bw`-wide strip down one side of an (x, y, w, h) box with corner radius r.
    The outer edge follows the box's corner arcs and the inner edge is straight, so the
    strip stays inside the rounded outline. Drawn for the left side, mirrored for right."""
    bw, r = min(bw, w / 2), min(r, h / 2)
    if r <= 0:
        pts = [(0, 0), (bw, 0), (bw, h), (0, h)]
        segs = [("M", *pts[0])] + [("L", *p) for p in pts[1:]]
    elif bw < r:  # inner edge cuts the corner arc at height dy below the top
        dy = r - math.sqrt(r * r - (r - bw) ** 2)
        segs = [("M", 0, r), ("A", r, r, 0, 0, 1, bw, dy), ("L", bw, h - dy), ("A", r, r, 0, 0, 1, 0, h - r)]
    else:  # strip wider than the radius: full corner arc, then straight along top/bottom
        segs = [("M", 0, r), ("A", r, r, 0, 0, 1, r, 0), ("L", bw, 0), ("L", bw, h), ("L", r, h), ("A", r, r, 0, 0, 1, 0, h - r)]
    segs.append(("Z",))
    flip = side != "left"

    def place(s):
        if s[0] == "A":  # (A, rx, ry, rot, large, sweep, px, py): mirroring flips the sweep
            _, rx, ry, rot, large, sweep, px_, py_ = s
            return ("A", rx, ry, rot, large, 1 - sweep if flip else sweep, x + (w - px_ if flip else px_), y + py_)
        if s[0] == "Z":
            return s
        return (s[0], x + (w - s[1] if flip else s[1]), y + s[2])

    return [place(s) for s in segs]


def poly_len(pts) -> float:
    return sum(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 for (x0, y0), (x1, y1) in zip(pts, pts[1:]))


class SceneBuilder:
    def __init__(self, doc: Document, router: Router):
        self.doc, self.router = doc, router
        self.edge_polys: dict[str, list[tuple[float, float]]] = {}
        self.title_needs: dict[str, float] = {}

    def build(self) -> Scene:
        root = self.doc.root
        edges_layer = Elem("group", cls="pdg-edges")
        edge_elems = [self.edge(e) for e in self.doc.edges]
        self.title_layer = Elem("group", cls="pdg-titles")
        groups_layer = Elem("group", cls="pdg-groups", children=[self.group(c) for c in root.children if isinstance(c, Group)])
        edges_layer.children = edge_elems
        nodes_layer = Elem("group", cls="pdg-nodes", children=[self.node(c) for c in self.doc.walk() if isinstance(c, Node)])
        layers = [groups_layer, edges_layer, nodes_layer]
        grid = self.grid(root)
        if grid:
            layers.insert(0, grid)
        if self.title_layer.children:
            layers.append(self.title_layer)
        w, h = root.w, root.h
        if self.doc.brackets:
            br, bw = self.brackets(w)
            layers.append(br)
            w += bw
        legend, lw, lh = self.legend(h)
        if legend:
            layers.append(legend)
            w, h = max(w, lw), h + lh
        cap = root.attrs.get("caption")
        if cap:
            st = root.part_styles.get("caption") or root.style
            fs = font_size(st, 12)
            cw, ch, lines = text_block(cap, st, 12)
            w = max(w, cw + 28)
            align = st.get("text-align", "center")
            x, anchor = {"left": (14, "start"), "right": (w - 14, "end")}.get(align, (w / 2, "middle"))
            layers.append(Elem("group", cls="pdg-caption", children=self.text(lines, x, h, fs, st, anchor)))
            h += ch + 14
        return Scene(w, h, root.style.get("background"), layers)

    def brackets(self, right: float) -> tuple[Elem, float]:
        """`bracket a, b "note"`: a curly bracket right of the diagram spanning the listed
        items top to bottom, the note beside it. Brackets that overlap vertically are
        stacked outward. Returns the layer and the extra canvas width."""
        out = Elem("group", cls="pdg-brackets")
        depth = 8.0
        spans = []  # (height, y0, y1, bracket, text width, text height, lines)
        for b in self.doc.brackets:
            items = [self.doc.items[i] for i in b.ids]
            y0, y1 = min(i.ay for i in items), max(i.ay + i.h for i in items)
            spans.append((y1 - y0, y0, y1, b, *text_block(b.label, b.style, 11)))
        spans.sort(key=lambda s: s[0])  # short spans nearest the diagram, long ones outside
        cols: list[list[tuple[float, float]]] = []
        col_w: list[float] = []
        placed = []
        for _, y0, y1, b, tw, th, lines in spans:
            col = 0
            while col < len(cols) and any(not (y1 < a or y0 > z) for a, z in cols[col]):
                col += 1
            if col == len(cols):
                cols.append([])
                col_w.append(0.0)
            cols[col].append((y0, y1))
            col_w[col] = max(col_w[col], 2 * depth + 6 + tw + 14)
            placed.append((col, y0, y1, b, th, lines))
        for col, y0, y1, b, th, lines in placed:
            st, fs = b.style, font_size(b.style, 11)
            x = right + 4 + sum(col_w[:col])
            ym = (y0 + y1) / 2
            q = min(depth, (y1 - y0) / 4)
            segs = [
                ("M", x, y0),
                ("Q", x + depth, y0, x + depth, y0 + q),
                ("L", x + depth, ym - q),
                ("Q", x + depth, ym, x + 2 * depth, ym),
                ("Q", x + depth, ym, x + depth, ym + q),
                ("L", x + depth, y1 - q),
                ("Q", x + depth, y1, x, y1),
            ]
            kids = [
                Elem(
                    "path",
                    cls="pdg-bracket-line",
                    geom={"segs": segs},
                    paint={
                        "fill": "none",
                        "stroke": st.get("stroke", "#9ca3af"),
                        "stroke-width": px(st.get("stroke-width"), 1.5),
                        "stroke-linecap": "round",
                    },
                )
            ]
            kids += self.text(lines, x + 2 * depth + 6, ym - th / 2, fs, st, "start")
            out.children.append(Elem("group", cls=" ".join(["pdg-bracket"] + b.classes), children=kids))
        return out, 4 + sum(col_w)

    def legend(self, top: float) -> tuple[Elem | None, float, float]:
        """`legend .cls "text"` entries: a key box under the diagram, swatches styled like nodes."""
        entries = self.doc.legend
        if not entries:
            return None, 0.0, 0.0
        st = self.doc.root.part_styles.get("legend") or {}
        st = {"font-family": self.doc.root.style.get("font-family", "sans-serif"), **st}
        fs = font_size(st, 11)
        sw, gap, pad = 14.0, 16.0, 10.0
        title = self.doc.legend_title
        tw, _, _ = text_block(title, st, 11, bold=True)
        x = pad + (tw + gap if title else 0.0)
        kids, row_h = [], max(sw, fs * LINE_H)
        y0 = top + pad
        ty = y0 + (row_h - fs * LINE_H) / 2  # text top, vertically centred in the row
        if title:
            kids += self.text([title], 14 + pad, ty, fs, {**st, "font-weight": "bold"}, "start")
        for n in entries:
            ew, _, _ = text_block(n.label, st, 11, bold=False)
            ns = n.style
            r = min(px(ns.get("border-radius"), 3), 4)
            kids.append(
                Elem(
                    "rect",
                    cls=" ".join(["pdg-legend-swatch"] + n.classes),
                    geom={"x": 14 + x, "y": y0 + (row_h - sw) / 2, "w": sw, "h": sw, "rx": r},
                    paint={"fill": ns.get("fill", "#ffffff"), "stroke": ns.get("stroke", "#9ca3af"), "stroke-width": 1.2},
                )
            )
            kids += self.text([n.label], 14 + x + sw + 6, ty, fs, st, "start")
            x += sw + 6 + ew + gap
        bw, bh = x - gap + pad, row_h + 2 * pad
        box = Elem(
            "rect",
            cls="pdg-legend-box",
            geom={"x": 14, "y": top, "w": bw, "h": bh, "rx": 6},
            paint={"fill": st.get("fill", "#ffffff"), "stroke": st.get("stroke", "#d1d5db"), "stroke-width": 1},
        )
        return Elem("group", cls="pdg-legend", children=[box] + kids), bw + 28, bh + 14

    @staticmethod
    def text_paint(st: dict, fs: float) -> dict:
        return {
            "fill": st.get("color", "#111827"),
            "font-family": st.get("font-family", "sans-serif"),
            "font-size": fs,
            "font-weight": st.get("font-weight", "normal"),
            "font-style": st.get("font-style", "normal"),
        }

    @classmethod
    def text(cls, lines, cx, top, fs, st, anchor="middle") -> list[Elem]:
        lh = fs * LINE_H
        paint = cls.text_paint(st, fs)
        return [
            Elem("text", geom={"x": cx, "y": top + lh * i + fs * 0.95, "text": line, "anchor": anchor}, paint=dict(paint))
            for i, line in enumerate(lines)
        ]

    def shape(self, n, shape: str, st: dict) -> list[Elem]:
        x, y, w, h = n.ax, n.ay, n.w, n.h
        stroke = st.get("stroke", "none")
        sw = px(st.get("stroke-width"), 1)
        paint = {"fill": st.get("fill", "#fff"), "stroke": stroke, "stroke-width": sw}
        if st.get("stroke-dasharray"):
            paint["stroke-dasharray"] = st["stroke-dasharray"]
        if st.get("opacity"):
            paint["opacity"] = st["opacity"]
        if st.get("shadow") == "soft":
            paint["filter"] = "shadow"
        r = corner_radius(st, shape, w, h)
        if shape in ("box", "round", "pill", "note", "square"):
            el = Elem("rect", geom={"x": x, "y": y, "w": w, "h": h, "rx": r}, paint=paint)
        elif shape in ("circle", "ellipse"):
            el = Elem("ellipse", geom={"cx": n.cx, "cy": n.cy, "rx": w / 2, "ry": h / 2}, paint=paint)
        elif shape == "diamond":
            el = Elem("polygon", geom={"points": [(n.cx, y), (x + w, n.cy), (n.cx, y + h), (x, n.cy)]}, paint=paint)
        elif shape == "hexagon":
            k = h / 2 * 0.6
            el = Elem(
                "polygon",
                geom={"points": [(x + k, y), (x + w - k, y), (x + w, n.cy), (x + w - k, y + h), (x + k, y + h), (x, n.cy)]},
                paint=paint,
            )
        elif shape == "cylinder":
            e = 6.0
            body = Elem(
                "path",
                geom={
                    "segs": [
                        ("M", x, y + e),
                        ("A", w / 2, e, 0, 0, 1, x + w, y + e),
                        ("L", x + w, y + h - e),
                        ("A", w / 2, e, 0, 0, 1, x, y + h - e),
                        ("Z",),
                    ]
                },
                paint=paint,
            )
            lid = Elem(
                "path",
                geom={"segs": [("M", x, y + e), ("A", w / 2, e, 0, 0, 0, x + w, y + e)]},
                paint={"fill": "none", "stroke": stroke, "stroke-width": sw},
            )
            return [body, lid]
        else:
            return []
        mode = st.get("border", "none")
        if mode in BORDER_MODES and stroke != "none":
            dur = seconds(st.get("border-speed"), 1.6)
            dash = st.get("stroke-dasharray")
            if mode == "march" and not dash:
                dash = f"{max(4.0, sw * 4):g} {max(3.0, sw * 3):g}"
                el.paint["stroke-dasharray"] = dash
            if mode == "glow":
                halo = Elem(
                    el.kind,
                    cls="pdg-border-glow",
                    geom=dict(el.geom),
                    paint={"fill": "none", "stroke": stroke, "stroke-width": sw},
                    tracks=border_tracks("glow", sw, dash, dur),
                )
                return [halo, el]
            el.tracks = border_tracks(mode, sw, dash, dur)
        return [el]

    def node(self, n: Node) -> Elem:
        st = n.style
        shape = n.attrs.get("shape", "box")
        out = Elem("group", id=n.id, cls=" ".join(["pdg-node"] + n.classes), children=self.shape(n, shape, st))
        out.children += self.accent(n, st) + self.corner_marks(n, st)
        fs = font_size(st, 14)
        if n.image:
            img = n.image
            ix = n.cx - img["dw"] / 2
            gap = 4 if n.text_lines else 0
            block = img["dh"] + gap + n.text_h
            iy = n.ay + (n.h - block) / 2 if shape != "image" else n.ay
            out.children.append(Elem("image", geom={"x": ix, "y": iy, "w": img["dw"], "h": img["dh"], "href": img["href"]}))
            out.children += self.text(n.text_lines, n.cx, iy + img["dh"] + gap, fs, st)
        else:
            out.children += self._node_text(n, st, fs)
        return out

    def _node_text(self, n, st, fs):
        align = st.get("text-align", "center")
        pt, pr, pb, pl = node_padding(st)
        top = n.cy - n.text_h / 2
        x, anchor = {"left": (n.ax + pl, "start"), "right": (n.ax + n.w - pr, "end")}.get(align, (n.cx, "middle"))
        out = self.text(n.text_lines, x, top, fs, st, anchor)
        if n.sub_lines:
            sst = n.sub_style or st
            stop = top + n.text_h - n.sub_h + SUB_GAP
            out += self.text(n.sub_lines, x, stop, font_size(sst, 12), sst, anchor)
        return out

    def accent(self, it, st) -> list[Elem]:
        """`accent-bar: 4px #22c55e`: a strip along one side (`accent-side`), clipped to the
        box's own rounded corners so it never pokes outside them."""
        a = accent(st)
        if not a:
            return []
        bw, color, side = a
        r = min(corner_radius(st, it.attrs.get("shape", "box"), it.w, it.h), it.h / 2)
        return [
            Elem(
                "path",
                cls="pdg-accent",
                geom={"segs": accent_segs(it.ax, it.ay, it.w, it.h, bw, r, side)},
                paint={"fill": color or st.get("stroke", "#22c55e")},
            )
        ]

    def group(self, g: Group) -> Elem:
        st = g.style
        out = Elem(
            "group",
            id=g.id,
            cls=" ".join(["pdg-group"] + g.classes),
            children=self.shape(self._frame(g, st), g.attrs.get("shape", "box"), st),
        )
        out.children += self.accent(g, st)
        if g.label and title_position(st) == "left":
            out.children.append(self._side_title(g, st))
        elif g.label:
            if has_title_band(st) and title_position(st) != "above":
                out.children.append(self._title_band(g, st))
            self._top_title(g, st, out)
        for c in g.children:
            if isinstance(c, Group):
                out.children.append(self.group(c))
        return out

    @staticmethod
    def _frame(g: Group, st: dict):
        """`label-position: above`: the outline starts below the title strip."""
        if not (g.label and title_position(st) == "above"):
            return g
        return SimpleNamespace(ax=g.ax, ay=g.ay + g.label_h, w=g.w, h=g.h - g.label_h)

    def _title_band(self, g: Group, st: dict) -> Elem:
        """`title-fill`: a band behind the title, rounded like the group's top corners."""
        bh = box4(st.get("padding"), 14)[0] + g.label_h - 3
        r = min(corner_radius(st, g.attrs.get("shape", "box"), g.w, g.h), bh)
        return Elem(
            "path",
            cls="pdg-title-band",
            paint={"fill": st["title-fill"]},
            geom={
                "segs": [
                    ("M", g.ax, g.ay + bh),
                    ("L", g.ax, g.ay + r),
                    ("A", r, r, 0, 0, 1, g.ax + r, g.ay),
                    ("L", g.ax + g.w - r, g.ay),
                    ("A", r, r, 0, 0, 1, g.ax + g.w, g.ay + r),
                    ("L", g.ax + g.w, g.ay + bh),
                    ("Z",),
                ]
            },
        )

    def _side_title(self, g: Group, st: dict) -> Elem:
        """`label-position: left`: the title turned 90°, pinned near the left edge (padding
        moves the content, not the title, so an edge can pass between them)."""
        fs = font_size(st, 12)
        x = g.ax + 8 + g.side_w / 2 + fs * 0.35
        return Elem(
            "text",
            geom={"x": x, "y": g.cy, "text": g.label.replace("\n", " "), "anchor": "middle", "rotate": -90},
            paint=self.text_paint(st, fs),
        )

    def _top_title(self, g: Group, st: dict, out: Elem) -> None:
        """Title (and `sub=` line) at the top or bottom, sliding clear of crossing edges."""
        fs = font_size(st, 12)
        pt, pr, pb, pl = box4(st.get("padding"), 14)
        tw, th, _ = text_block(g.label, st, 12)
        bottom = title_position(st) == "bottom"
        above = title_position(st) == "above"
        top = g.ay + g.h - pb - g.label_h + 6 if bottom else g.ay + (0 if above else pt)
        x0 = g.ax if above else self._title_x(g, st, tw, pl, pr, top, th)
        box = (x0 - TITLE_PAD, top - 2, x0 + tw + TITLE_PAD, top + th + 2)
        texts = self.text(g.label.split("\n"), x0, top, fs, st, "start")
        if g.attrs.get("sub") and not bottom:
            sst = g.sub_style or st
            texts += self.text(g.attrs["sub"].split("\n"), x0, top + g.title_h + SUB_GAP, font_size(sst, 11), sst, "start")
        xs = self._crossings(box[1], box[3], box[0], box[2])
        if not xs:
            out.children += texts
            return
        # ask the pipeline for a wider group: children are centred, so widening by d
        # moves the crossing edges d/2 away from the left-aligned title
        self.title_needs[g.id] = 2 * max(box[2] + 2 - min(xs), 0.0) + 4
        # nowhere free to slide to: lift the title above the edges on a patch of the
        # group's own fill, so the line visibly stops around the text
        fill = st.get("fill", "none")
        if fill in ("none", "transparent"):
            fill = self.doc.root.style.get("background", "#ffffff")
        patch = Elem(
            "rect",
            cls="pdg-title-bg",
            geom={"x": box[0], "y": box[1], "w": box[2] - box[0], "h": box[3] - box[1], "rx": 3},
            paint={"fill": fill},
        )
        self.title_layer.children.append(Elem("group", cls="pdg-group-title", children=[patch] + texts))

    def _title_x(self, g, st, tw, pl, pr, top, th) -> float:
        """Preferred x from text-align; slide along the title band if edges cross there."""
        align = st.get("text-align", "left")
        lo, hi = g.ax + pl, g.ax + g.w - pr - tw
        pref = {"center": g.cx - tw / 2, "right": hi}.get(align, lo)
        if hi <= lo:
            return lo
        blocked = sorted(self._crossings(top - 2, top + th + 2, g.ax, g.ax + g.w))
        if not any(pref - TITLE_PAD < x < pref + tw + TITLE_PAD for x in blocked):
            return pref
        # candidate positions: just right / left of every crossing, and the band ends
        cands = [lo, hi] + [x + TITLE_PAD + 2 for x in blocked] + [x - tw - TITLE_PAD - 2 for x in blocked]
        ok = [c for c in cands if lo <= c <= hi and not any(c - TITLE_PAD < x < c + tw + TITLE_PAD for x in blocked)]
        return min(ok, key=lambda c: abs(c - pref)) if ok else pref

    def _crossings(self, y0, y1, xa, xb) -> list[float]:
        xs = []
        for poly in self.edge_polys.values():
            for (ax, ay), (bx, by) in zip(poly, poly[1:]):
                if ay == by or not (min(ay, by) <= y1 and max(ay, by) >= y0):
                    continue
                for yy in (max(y0, min(ay, by)), min(y1, max(ay, by))):
                    t = (yy - ay) / (by - ay)
                    x = ax + (bx - ax) * t
                    if xa <= x <= xb:
                        xs.append(x)
        return xs

    def edge(self, e: Edge) -> Elem:
        st = e.style
        R = self.router
        pts, axis = R.geometry(e)
        route = st.get("route", "curve")
        color = st.get("stroke", "#4b5563")
        width = px(st.get("stroke-width"), 1.5)
        if e.body == "thick" and "width" not in e.attrs:
            width *= 2.5
        dash = st.get("stroke-dasharray")
        if e.body == "dashed" and not dash:
            dash = f"{width * 3:.0f} {width * 2.5:.0f}"
        arrow = e.attrs.get("arrow", e.arrow if e.arrow != "none" or "arrow" not in st else st["arrow"])
        if "arrow" in st and "arrow" not in e.attrs and e.arrow == "end":
            arrow = st["arrow"]
        pts = list(pts)
        hl = px(st.get("head-size"), min(18.0, 6.0 + width * 2.2))
        free = route == "straight" or flow_dir(lca(self.doc.items[e.src], self.doc.items[e.dst], self.doc.root)) == "auto"

        def end_dir(tip, prev):
            if free or axis == "L":
                dx, dy = tip[0] - prev[0], tip[1] - prev[1]
            elif axis == "v":
                dx, dy = 0.0, tip[1] - prev[1]
            else:
                dx, dy = tip[0] - prev[0], 0.0
            n = math.hypot(dx, dy) or 1.0
            return dx / n, dy / n

        heads = []
        for end, nb, want, key in ((-1, -2, ("end", "both"), "head"), (0, 1, ("start", "both"), "head-start")):
            if arrow not in want:
                continue
            kind = st.get(key, st.get("head", "triangle"))
            tip = pts[end]
            dv = end_dir(tip, pts[nb])
            heads.append((kind, tip, dv))
            if kind not in ER_HEADS:  # stroke stops at the head's base; ER lines run to the box
                pts[end] = (tip[0] - dv[0] * hl * 0.9, tip[1] - dv[1] * hl * 0.9)
        stub = px(st["stub"]) if "stub" in st else None
        if stub is not None and heads:
            stub += hl
        radius = px(st.get("radius"), 12 if route == "bend" else 6)
        diag = Diagonal.from_style(st, route)
        level = R.level(e)
        segs = R.path_segs(pts, axis, route, radius, stub, level, diag)
        self.edge_polys[e.id] = R.polyline(pts, axis, route, radius, stub, level, diag)

        cls = " ".join(["pdg-edge"] + e.classes)
        flow = st.get("flow", "none")
        if flow == "auto":
            flow = {"end": "forward", "start": "reverse", "both": "both"}.get(arrow, "forward")
        flowing = flow in ("forward", "reverse", "both")
        if flowing:
            cls += f" pdg-flow pdg-flow-{flow}"
        out = Elem("group", id=e.id, cls=cls)
        base = {"fill": "none", "stroke": color, "stroke-linejoin": "round"}
        if flow == "draw":
            cls += " pdg-draw"
            out.cls = cls
            L = poly_len(self.edge_polys[e.id]) + 2
            out.children.append(
                Elem(
                    "path",
                    cls="pdg-line",
                    geom={"segs": segs},
                    paint=dict(
                        base,
                        **{"stroke-width": width, "stroke-linecap": "butt" if heads else "round", "stroke-dasharray": f"{L:.1f} {L:.1f}"},
                    ),
                    tracks=draw_tracks(L, seconds(st.get("flow-speed"), 3.0)),
                )
            )
        elif not flowing:
            p = dict(base, **{"stroke-width": width, "stroke-linecap": "butt" if heads else "round"})
            if dash:
                p["stroke-dasharray"] = dash
            out.children.append(Elem("path", cls="pdg-line", geom={"segs": segs}, paint=p))
        else:
            fdash = dash or f"0.1 {max(6.0, width * 4):g}"
            fwidth = width if dash else max(width * 1.8, 2.5)
            dur = seconds(st.get("flow-speed"), 1.2)
            if not dash:  # faint guide line under the moving dots
                out.children.append(
                    Elem(
                        "path",
                        cls="pdg-line",
                        geom={"segs": segs},
                        paint=dict(base, **{"stroke-width": max(0.75, width * 0.5), "stroke-opacity": 0.3}),
                    )
                )
            dirs = ["forward", "reverse"] if flow == "both" else [flow]
            ring = not dash and st.get("flow-dot", "dot").strip() == "ring"
            if ring:
                fwidth, fdash = max(fwidth, 8.0), f"0.1 {max(24.0, width * 10):g}"
                rp = list(pts)
                for i, j in ((0, 1), (-1, -2)):
                    dv = end_dir(rp[i], rp[j])
                    rp[i] = (rp[i][0] - dv[0] * fwidth, rp[i][1] - dv[1] * fwidth)
                segs = R.path_segs(rp, axis, route, radius, stub, level, diag)
            for k, fd in enumerate(dirs):
                tracks = flow_tracks(fdash, dur, fd == "reverse")
                if flow == "both" and k == 1:
                    tracks = [t.shifted(dash_len(fdash) / 2) for t in tracks]
                out.children.append(
                    Elem(
                        "path",
                        cls=f"pdg-line pdg-flow-{fd}",
                        geom={"segs": segs},
                        paint=dict(base, **{"stroke-width": fwidth, "stroke-dasharray": fdash, "stroke-linecap": "round"}),
                        tracks=tracks,
                    )
                )
                if ring:  # hollow dot: same moving pattern, background colour, narrower
                    out.children.append(
                        Elem(
                            "path",
                            cls="pdg-line pdg-flow-ring",
                            geom={"segs": segs},
                            paint=dict(
                                base,
                                **{
                                    "stroke": self.doc.root.style.get("background", "#ffffff"),
                                    "stroke-width": fwidth - 4,
                                    "stroke-dasharray": fdash,
                                    "stroke-linecap": "round",
                                },
                            ),
                            tracks=tracks,
                        )
                    )
        for kind, tip, dvec in heads:
            out.children.append(self.head(kind, tip, dvec, hl, color, width, self.doc.root.style.get("background", "#ffffff")))
        if e.label:
            lab = self.edge_label(e, self.edge_polys[e.id])
            out.children += lab
        if e.attrs.get("step"):
            box = lab[0].geom if e.label else None
            out.children += self.step_badge(e, self.edge_polys[e.id], box)
        return out

    def corner_marks(self, n, st) -> list[Elem]:
        """`corner-marks: 8px`: short L ticks just outside each corner of the node box."""
        k = px(st.get("corner-marks"), 0)
        if k <= 0:
            return []
        o = 4
        x0, y0, x1, y1 = n.ax - o, n.ay - o, n.ax + n.w + o, n.ay + n.h + o
        segs = []
        for x, y, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            segs += [("M", x + dx * k, y), ("L", x, y), ("L", x, y + dy * k)]
        col = st.get("stroke") or st.get("--border") or "#888888"
        return [Elem("path", cls="pdg-corners", geom={"segs": segs}, paint={"fill": "none", "stroke": col, "stroke-width": 1})]

    def grid(self, root):
        """`grid=N` on the graph: faint N px background grid (decoration only)."""
        n = px(root.attrs.get("grid") or root.style.get("grid"), 0)
        if n < 4:
            return None
        segs = []
        for i in range(1, int(root.w // n) + 1):
            segs += [("M", i * n, 0), ("L", i * n, root.h)]
        for j in range(1, int(root.h // n) + 1):
            segs += [("M", 0, j * n), ("L", root.w, j * n)]
        col = root.style.get("grid-color") or root.style.get("--border") or "#888888"
        return Elem(
            "group",
            cls="pdg-grid",
            children=[Elem("path", geom={"segs": segs}, paint={"fill": "none", "stroke": col, "stroke-width": 1, "stroke-opacity": 0.35})],
        )

    def step_badge(self, e, poly, label_box=None) -> list[Elem]:
        """Numbered circle for an edge. Next to the label when there is one; on the line a
        third of the way along when the edge is long enough to hold it with room to spare;
        otherwise beside the middle of the edge, so a short arrow between stacked boxes
        stays a visible line and the circle never sits on a box."""
        st = e.step_style or e.style
        st = {**st, "font-weight": st.get("font-weight", "bold")}
        fs = font_size(st, 11)
        txt = e.attrs["step"][:3]
        w, h, _ = text_block(txt, st, 11)
        r = max(w, h) / 2 + 3
        if label_box:
            cx, cy = label_box["x"] - r - 3, label_box["y"] + label_box["h"] / 2
        else:
            cx, cy = self._step_spot(e, poly, r)
        circ = Elem(
            "circle",
            cls="pdg-step",
            geom={"cx": cx, "cy": cy, "r": r},
            paint={"fill": st.get("fill", "#374151"), "stroke": self.doc.root.style.get("background", "#ffffff"), "stroke-width": 1.5},
        )
        return [circ] + self.text([txt], cx, cy - fs * LINE_H / 2, fs, st)

    STEP_ROOM = 3.0  # an edge must be this many circle diameters long to carry its step

    def _step_spot(self, e, poly, r) -> tuple[float, float]:
        """Where a label-less step circle goes (see step_badge)."""
        length = sum(math.dist(a, b) for a, b in zip(poly, poly[1:]))
        on_line = point_along(poly, 1 / 3)
        if length >= self.STEP_ROOM * 2 * r and not self._on_a_box(on_line, r, e):
            return on_line
        mx, my = point_along(poly, 1 / 2)
        # the segment holding the midpoint gives the edge's direction there
        ax, ay, bx, by = *poly[0], *poly[-1]
        acc, half = 0.0, length / 2
        for a, b in zip(poly, poly[1:]):
            seg = math.dist(a, b)
            if acc + seg >= half:
                (ax, ay), (bx, by) = a, b
                break
            acc += seg
        d = math.hypot(bx - ax, by - ay) or 1.0
        nx, ny = -(by - ay) / d, (bx - ax) / d
        off = r + 4
        sides = [(mx - nx * off, my - ny * off), (mx + nx * off, my + ny * off)]
        if abs(by - ay) >= abs(bx - ax):  # vertical-ish edge: prefer the left side
            sides.sort(key=lambda p: p[0])
        else:  # horizontal-ish edge: prefer above
            sides.sort(key=lambda p: p[1])
        free = [p for p in sides if not self._on_a_box(p, r, e)]
        return (free or sides)[0]

    def _on_a_box(self, p, r, e) -> bool:
        """Would a circle of radius r at p overlap any node box (with a small margin)?"""
        x, y = p
        for n in self.doc.walk():
            if isinstance(n, Group):
                continue
            if n.ax - r - 2 < x < n.ax + n.w + r + 2 and n.ay - r - 2 < y < n.ay + n.h + r + 2:
                return True
        return False

    @staticmethod
    def head(kind, tip, d, hl, color, width, bg="#ffffff") -> Elem:
        """Arrowhead as plain geometry: tip sits exactly on the target outline.
        ER heads (crow's foot): one, many, zero-one, zero-many, one-many."""
        tx, ty = tip
        ux, uy = d
        nx, ny = -uy, ux
        hw = max(hl * 0.42, width * 1.2)

        def P(a, b):  # a along -d from tip, b along normal
            return (tx - ux * a + nx * b, ty - uy * a + ny * b)

        line = {"fill": "none", "stroke": color, "stroke-width": max(1.2, width)}
        bar = lambda a: Elem("polyline", geom={"points": [P(a, hw), P(a, -hw)]}, paint=line)  # noqa: E731
        crow = Elem("polyline", geom={"points": [P(0, hw), P(hl, 0), P(0, -hw)]}, paint=line)
        ring = Elem("circle", geom={"cx": P(hl * 1.5, 0)[0], "cy": P(hl * 1.5, 0)[1], "r": hw * 0.6}, paint=dict(line, fill=bg))
        er = {
            "one": [bar(hl * 0.5), bar(hl * 0.9)],
            "many": [crow],
            "zero-one": [bar(hl * 0.5), ring],
            "zero-many": [crow, ring],
            "one-many": [crow, bar(hl * 1.3)],
        }
        if kind in ER_HEADS:
            return Elem("group", cls="pdg-head", children=er[kind])
        shapes = {
            "open": ("polyline", [P(hl, hw), P(0, 0), P(hl, -hw)], dict(line, **{"stroke-linejoin": "miter"})),
            "diamond": ("polygon", [P(0, 0), P(hl / 2, hw), P(hl, 0), P(hl / 2, -hw)], {"fill": color}),
            "bar": ("polyline", [P(0, hw), P(0, -hw)], dict(line, **{"stroke-width": max(2, width)})),
        }
        if kind == "dot":
            c = P(hl / 2.2, 0)
            return Elem("circle", cls="pdg-head", geom={"cx": c[0], "cy": c[1], "r": hl / 2.2}, paint={"fill": color})
        tag, pts, paint = shapes.get(kind, ("polygon", [P(0, 0), P(hl, hw), P(hl, -hw)], {"fill": color}))
        return Elem(tag, cls="pdg-head", geom={"points": pts}, paint=paint)

    def edge_label(self, e, poly) -> list[Elem]:
        st = e.label_style or e.style
        fs = font_size(st, 11)
        w, h, lines = text_block(e.label, st, 11, bold=False)  # same call as layout.label_gaps
        # bent edges: the run into the target is the edge's own (a fan-out bus is shared),
        # so labels go there when it fits; otherwise the longest run
        segs = list(zip(poly, poly[1:]))
        fits = len(segs) > 1 and math.dist(*segs[-1]) >= h + 4
        best = segs[-1] if fits else max(segs, key=lambda s: math.dist(*s))
        (ax, ay), (bx, by) = best
        t = 0.5
        lvl = (
            self.router.bend_level.get(e.id)
            if any(o is not e and o.src == e.src and self.router.bend_level.get(o.id) is not None for o in self.doc.edges)
            else None
        )
        if len(segs) == 1 and lvl is not None:  # straight sibling of a fan-out: below the bus too
            v = abs(bx - ax) < abs(by - ay)
            a0, a1 = (ay, by) if v else (ax, bx)
            if min(a0, a1) < lvl < max(a0, a1):
                t = ((lvl + a1) / 2 - a0) / (a1 - a0)
        mx, my = ax + (bx - ax) * t, ay + (by - ay) * t
        bg = st.get("background", self.doc.root.style.get("background", "#ffffff"))
        box = Elem(
            "rect",
            cls="pdg-label-bg",
            geom={"x": mx - w / 2 - 3, "y": my - h / 2 - 1, "w": w + 6, "h": h + 2, "rx": 3},
            paint={"fill": bg, "fill-opacity": 0.9},
        )
        return [box] + self.text(lines, mx, my - h / 2, fs, st)
