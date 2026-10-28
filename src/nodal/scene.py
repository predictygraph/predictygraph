"""AST + layout + routing -> Scene IR.

Also owns the decisions that need the routed geometry of everything at once:
* group titles slide along their top edge to a span no edge crosses; if no span is
  wide enough the title is lifted above the edges on a patch of the group's fill, so
  the crossing line stops around the text (plain geometry: works in every renderer);
* edge labels sit on the longest straight run of their own edge.
"""
from __future__ import annotations

import math

from .anim import BORDER_MODES, Track, border_tracks, dash_len, flow_tracks, seconds
from .ir import Elem, Scene
from .model import Document, Edge, Group, Node
from .route import Diagonal, Router, flow_dir, lca
from .style import box4, px
from .text import measure

TITLE_PAD = 6.0
ER_HEADS = ("one", "many", "zero-one", "zero-many", "one-many")


class SceneBuilder:
    def __init__(self, doc: Document, router: Router):
        self.doc, self.router = doc, router
        self.edge_polys: dict[str, list[tuple[float, float]]] = {}
        self.title_needs: dict[str, float] = {}

    # ------------------------------------------------------------ public
    def build(self) -> Scene:
        root = self.doc.root
        edges_layer = Elem("group", cls="nodal-edges")
        edge_elems = [self.edge(e) for e in self.doc.edges]
        self.title_layer = Elem("group", cls="nodal-titles")
        groups_layer = Elem("group", cls="nodal-groups",
                            children=[self.group(c) for c in root.children if isinstance(c, Group)])
        edges_layer.children = edge_elems
        nodes_layer = Elem("group", cls="nodal-nodes",
                           children=[self.node(c) for c in self.doc.walk() if isinstance(c, Node)])
        layers = [groups_layer, edges_layer, nodes_layer]
        if self.title_layer.children:
            layers.append(self.title_layer)
        return Scene(root.w, root.h, root.style.get("background"), layers)

    # ------------------------------------------------------------ text
    @staticmethod
    def text(lines, cx, top, fs, st, anchor="middle") -> list[Elem]:
        lh = fs * 1.25
        paint = {"fill": st.get("color", "#111827"), "font-family": st.get("font-family", "sans-serif"),
                 "font-size": fs, "font-weight": st.get("font-weight", "normal"),
                 "font-style": st.get("font-style", "normal")}
        return [Elem("text", geom={"x": cx, "y": top + lh * i + fs * 0.95, "text": line, "anchor": anchor},
                     paint=dict(paint)) for i, line in enumerate(lines)]

    # ------------------------------------------------------------ shapes
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
        r = px(st.get("border-radius"), 0)
        if shape == "round":
            r = max(r, 10)
        if shape == "pill":
            r = h / 2
        if shape in ("box", "round", "pill", "note", "square"):
            el = Elem("rect", geom={"x": x, "y": y, "w": w, "h": h, "rx": r}, paint=paint)
        elif shape in ("circle", "ellipse"):
            el = Elem("ellipse", geom={"cx": n.cx, "cy": n.cy, "rx": w / 2, "ry": h / 2}, paint=paint)
        elif shape == "diamond":
            el = Elem("polygon", geom={"points": [(n.cx, y), (x + w, n.cy), (n.cx, y + h), (x, n.cy)]}, paint=paint)
        elif shape == "hexagon":
            k = h / 2 * 0.6
            el = Elem("polygon", geom={"points": [(x + k, y), (x + w - k, y), (x + w, n.cy), (x + w - k, y + h),
                                                  (x + k, y + h), (x, n.cy)]}, paint=paint)
        elif shape == "cylinder":
            e = 6.0
            body = Elem("path", geom={"segs": [("M", x, y + e), ("A", w / 2, e, 0, 0, 1, x + w, y + e),
                                               ("L", x + w, y + h - e), ("A", w / 2, e, 0, 0, 1, x, y + h - e),
                                               ("Z",)]}, paint=paint)
            lid = Elem("path", geom={"segs": [("M", x, y + e), ("A", w / 2, e, 0, 0, 0, x + w, y + e)]},
                       paint={"fill": "none", "stroke": stroke, "stroke-width": sw})
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
                halo = Elem(el.kind, cls="nodal-border-glow", geom=dict(el.geom),
                            paint={"fill": "none", "stroke": stroke, "stroke-width": sw},
                            tracks=border_tracks("glow", sw, dash, dur))
                return [halo, el]
            el.tracks = border_tracks(mode, sw, dash, dur)
        return [el]

    def node(self, n: Node) -> Elem:
        st = n.style
        shape = n.attrs.get("shape", "box")
        out = Elem("group", id=n.id, cls=" ".join(["nodal-node"] + n.classes), children=self.shape(n, shape, st))
        fs = px(st.get("font-size"), 14)
        if n.image:
            img = n.image
            ix = n.cx - img["dw"] / 2
            gap = 4 if n.text_lines else 0
            block = img["dh"] + gap + n.text_h
            iy = n.ay + (n.h - block) / 2 if shape != "image" else n.ay
            out.children.append(Elem("image", geom={"x": ix, "y": iy, "w": img["dw"], "h": img["dh"],
                                                    "href": img["href"]}))
            out.children += self.text(n.text_lines, n.cx, iy + img["dh"] + gap, fs, st)
        else:
            out.children += self._node_text(n, st, fs)
        return out

    def _node_text(self, n, st, fs):
        align = st.get("text-align", "center")
        pt, pr, pb, pl = box4(st.get("padding"), 8)
        top = n.cy - n.text_h / 2
        if align == "left":
            return self.text(n.text_lines, n.ax + pl, top, fs, st, "start")
        if align == "right":
            return self.text(n.text_lines, n.ax + n.w - pr, top, fs, st, "end")
        return self.text(n.text_lines, n.cx, top, fs, st)

    def group(self, g: Group) -> Elem:
        st = g.style
        out = Elem("group", id=g.id, cls=" ".join(["nodal-group"] + g.classes),
                   children=self.shape(g, g.attrs.get("shape", "box"), st))
        if g.label:
            fs = px(st.get("font-size"), 12)
            pt, pr, pb, pl = box4(st.get("padding"), 14)
            lines = g.label.split("\n")
            bold = st.get("font-weight", "normal") in ("bold", "600", "700")
            tw, th, _ = measure(g.label, st.get("font-family", "sans-serif"), fs, bold)
            bottom = st.get("label-position", "top") == "bottom"
            top = g.ay + g.h - pb - g.label_h + 6 if bottom else g.ay + pt
            x0 = self._title_x(g, st, tw, pl, pr, top, th)
            box = (x0 - TITLE_PAD, top - 2, x0 + tw + TITLE_PAD, top + th + 2)
            texts = self.text(lines, x0, top, fs, st, "start")
            xs = self._crossings(box[1], box[3], box[0], box[2])
            if xs:
                # ask the pipeline for a wider group: children are centred, so widening
                # by d moves the crossing edges d/2 away from the left-aligned title
                over = max(box[2] + 2 - min(xs), 0.0)
                self.title_needs[g.id] = 2 * over + 4
            if self._crossings(box[1], box[3], box[0], box[2]):
                # nowhere free to slide to: lift the title above the edges on a patch of
                # the group's own fill, so the line visibly stops around the text
                fill = st.get("fill", "none")
                if fill in ("none", "transparent"):
                    fill = self.doc.root.style.get("background", "#ffffff")
                patch = Elem("rect", cls="nodal-title-bg",
                             geom={"x": box[0], "y": box[1], "w": box[2] - box[0], "h": box[3] - box[1], "rx": 3},
                             paint={"fill": fill})
                self.title_layer.children.append(Elem("group", cls="nodal-group-title", children=[patch] + texts))
            else:
                out.children += texts
        for c in g.children:
            if isinstance(c, Group):
                out.children.append(self.group(c))
        return out

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

    # ------------------------------------------------------------ edges
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
        free = route == "straight" or flow_dir(lca(self.doc.items[e.src], self.doc.items[e.dst],
                                                   self.doc.root)) == "auto"

        def end_dir(tip, prev):
            if free or axis == "L":
                dx, dy = tip[0] - prev[0], tip[1] - prev[1]
            elif axis == "v":
                dx, dy = 0.0, tip[1] - prev[1]
            else:
                dx, dy = tip[0] - prev[0], 0.0
            l = math.hypot(dx, dy) or 1.0
            return dx / l, dy / l

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

        cls = " ".join(["nodal-edge"] + e.classes)
        flow = st.get("flow", "none")
        if flow == "auto":
            flow = {"end": "forward", "start": "reverse", "both": "both"}.get(arrow, "forward")
        flowing = flow in ("forward", "reverse", "both")
        if flowing:
            cls += f" nodal-flow nodal-flow-{flow}"
        out = Elem("group", id=e.id, cls=cls)
        base = {"fill": "none", "stroke": color, "stroke-linejoin": "round"}
        if not flowing:
            p = dict(base, **{"stroke-width": width, "stroke-linecap": "butt" if heads else "round"})
            if dash:
                p["stroke-dasharray"] = dash
            out.children.append(Elem("path", cls="nodal-line", geom={"segs": segs}, paint=p))
        else:
            fdash = dash or f"0.1 {max(6.0, width * 4):g}"
            fwidth = width if dash else max(width * 1.8, 2.5)
            dur = seconds(st.get("flow-speed"), 1.2)
            if not dash:  # faint guide line under the moving dots
                out.children.append(Elem("path", cls="nodal-line", geom={"segs": segs},
                                         paint=dict(base, **{"stroke-width": max(0.75, width * 0.5),
                                                             "stroke-opacity": 0.3})))
            dirs = ["forward", "reverse"] if flow == "both" else [flow]
            for k, fd in enumerate(dirs):
                tracks = flow_tracks(fdash, dur, fd == "reverse")
                if flow == "both" and k == 1:
                    tracks = [t.shifted(dash_len(fdash) / 2) for t in tracks]
                out.children.append(Elem("path", cls=f"nodal-line nodal-flow-{fd}", geom={"segs": segs},
                                         paint=dict(base, **{"stroke-width": fwidth, "stroke-dasharray": fdash,
                                                             "stroke-linecap": "round"}),
                                         tracks=tracks))
        for kind, tip, dvec in heads:
            out.children.append(self.head(kind, tip, dvec, hl, color, width,
                                          self.doc.root.style.get("background", "#ffffff")))
        if e.label:
            out.children += self.edge_label(e, self.edge_polys[e.id])
        return out

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
        ring = Elem("circle", geom={"cx": P(hl * 1.5, 0)[0], "cy": P(hl * 1.5, 0)[1], "r": hw * 0.6},
                    paint=dict(line, fill=bg))
        er = {"one": [bar(hl * 0.5), bar(hl * 0.9)], "many": [crow], "zero-one": [bar(hl * 0.5), ring],
              "zero-many": [crow, ring], "one-many": [crow, bar(hl * 1.3)]}
        if kind in ER_HEADS:
            return Elem("group", cls="nodal-head", children=er[kind])
        shapes = {
            "open": ("polyline", [P(hl, hw), P(0, 0), P(hl, -hw)], dict(line, **{"stroke-linejoin": "miter"})),
            "diamond": ("polygon", [P(0, 0), P(hl / 2, hw), P(hl, 0), P(hl / 2, -hw)], {"fill": color}),
            "bar": ("polyline", [P(0, hw), P(0, -hw)], dict(line, **{"stroke-width": max(2, width)})),
        }
        if kind == "dot":
            c = P(hl / 2.2, 0)
            return Elem("circle", cls="nodal-head", geom={"cx": c[0], "cy": c[1], "r": hl / 2.2}, paint={"fill": color})
        tag, pts, paint = shapes.get(kind, ("polygon", [P(0, 0), P(hl, hw), P(hl, -hw)], {"fill": color}))
        return Elem(tag, cls="nodal-head", geom={"points": pts}, paint=paint)

    def edge_label(self, e, poly) -> list[Elem]:
        st = e.label_style or e.style
        fs = px(st.get("font-size"), 11)
        w, h, lines = measure(e.label, st.get("font-family", "sans-serif"), fs)
        # bent edges: the run into the target is the edge's own (a fan-out bus is shared),
        # so labels go there when it fits; otherwise the longest run
        segs = list(zip(poly, poly[1:]))
        fits = len(segs) > 1 and math.dist(*segs[-1]) >= h + 4
        best = segs[-1] if fits else max(segs, key=lambda s: math.dist(*s))
        (ax, ay), (bx, by) = best
        t = 0.5
        lvl = self.router.bend_level.get(e.id) if any(
            o is not e and o.src == e.src and self.router.bend_level.get(o.id) is not None for o in self.doc.edges) else None
        if len(segs) == 1 and lvl is not None:  # straight sibling of a fan-out: below the bus too
            v = abs(bx - ax) < abs(by - ay)
            a0, a1 = (ay, by) if v else (ax, bx)
            if min(a0, a1) < lvl < max(a0, a1):
                t = ((lvl + a1) / 2 - a0) / (a1 - a0)
        mx, my = ax + (bx - ax) * t, ay + (by - ay) * t
        bg = st.get("background", self.doc.root.style.get("background", "#ffffff"))
        box = Elem("rect", cls="nodal-label-bg", geom={"x": mx - w / 2 - 3, "y": my - h / 2 - 1, "w": w + 6,
                                                       "h": h + 2, "rx": 3},
                   paint={"fill": bg, "fill-opacity": 0.9})
        return [box] + self.text(lines, mx, my - h / 2, fs, st)
