"""Static SVG renderer (no browser, presentation attributes + classes)."""
from __future__ import annotations

import math
from xml.sax.saxutils import escape, quoteattr

from .layout import direct_child
from .model import Document, Edge, Group, Node
from .style import box4, px

HEAD_LEN = 9.0


def lca(a, b, root):
    aa = [a] + a.ancestors()
    bb = set(id(x) for x in [b] + b.ancestors())
    for x in aa:
        if id(x) in bb and isinstance(x, Group):
            return x
    return root


def flow_dir(g: Group) -> str:
    if g.attrs.get("layout", "layered") in ("layered",):
        return g.attrs.get("dir", "TB").upper()
    if g.attrs.get("layout") == "row":
        return "LR"
    if g.attrs.get("layout") == "column":
        return "TB"
    return "auto"


def boundary_point(n, tx, ty, shape):
    """Intersection of ray centre->(tx,ty) with node outline."""
    cx, cy = n.cx, n.cy
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    hw, hh = n.w / 2, n.h / 2
    if shape in ("circle", "ellipse"):
        t = 1 / math.sqrt((dx / hw) ** 2 + (dy / hh) ** 2)
    elif shape == "diamond":
        t = 1 / (abs(dx) / hw + abs(dy) / hh)
    else:
        t = min(hw / abs(dx) if dx else math.inf, hh / abs(dy) if dy else math.inf)
    return cx + dx * t, cy + dy * t


def port(n, side):
    return {"top": (n.cx, n.ay), "bottom": (n.cx, n.ay + n.h),
            "left": (n.ax, n.cy), "right": (n.ax + n.w, n.cy)}[side]


class SvgRenderer:
    def __init__(self, doc: Document):
        self.doc = doc
        self.out: list[str] = []
        self.defs: dict[str, str] = {}

    # ------------------------------------------------------------ edges
    def prepare_edges(self):
        """Cross-edge bookkeeping: parallel-edge offsets and shared fan-in bend levels."""
        pairs: dict[tuple[str, str], list[Edge]] = {}
        for e in self.doc.edges:
            pairs.setdefault(tuple(sorted((e.src, e.dst))), []).append(e)
        self.offset = {}
        for es in pairs.values():
            n = len(es)
            for i, e in enumerate(es):
                k = (i - (n - 1) / 2) * 12
                # opposite-direction edges get mirrored sign so they stay apart
                self.offset[e.id] = k if e.src <= e.dst else -k
        self.bend_level = {}

    def _shared_bends(self):
        """Ortho fan-in/fan-out: edges sharing a target (or source) turn at one common
        level, so they merge into a single bus line (class-diagram style)."""
        geo = {e.id: self.edge_geometry(e) for e in self.doc.edges
               if e.style.get("route", "curve") == "ortho"}
        for key in ("dst", "src"):
            buckets: dict[str, list] = {}
            for e in self.doc.edges:
                if e.id in geo and geo[e.id][1] in ("v", "h") and len(geo[e.id][0]) == 2:
                    buckets.setdefault(getattr(e, key), []).append(e)
            for es in buckets.values():
                if len(es) < 2:
                    continue
                if any(e.id in self.bend_level for e in es):
                    continue
                axis = geo[es[0].id][1]
                i = 1 if axis == "v" else 0
                hub = [geo[e.id][0][-1 if key == "dst" else 0][i] for e in es]
                far = [geo[e.id][0][0 if key == "dst" else -1][i] for e in es]
                if len({round(h) for h in hub}) != 1 or len({geo[e.id][1] for e in es}) != 1:
                    continue
                h = hub[0]
                nearest = min(far, key=lambda f: abs(f - h))
                level = h + (nearest - h) / 2
                for e in es:
                    self.bend_level[e.id] = level

    def _ports(self, e, a, b, vert, sep):
        if vert:
            down = b.cy > a.cy
            return port(a, "bottom" if down else "top"), port(b, "top" if down else "bottom")
        right = b.cx > a.cx
        return port(a, "right" if right else "left"), port(b, "left" if right else "right")

    def edge_geometry(self, e: Edge):
        a, b = self.doc.items[e.src], self.doc.items[e.dst]
        owner = lca(a, b, self.doc.root)
        da, db = direct_child(a, owner), direct_child(b, owner)
        d = flow_dir(owner)
        route = e.style.get("route", "curve")
        wps = list(e.waypoints)
        off = self.offset.get(e.id, 0.0)
        # explicit ports: exit=/enter= top|bottom|left|right
        ex, en = e.attrs.get("exit"), e.attrs.get("enter")
        if ex or en:
            ex = ex or ("right" if b.cx > a.cx else "left")
            en = en or ("left" if b.cx > a.cx else "right")
            p0, p1 = port(a, ex), port(b, en)
            v0, v1 = ex in ("top", "bottom"), en in ("top", "bottom")
            if v0 != v1:  # L-shape: one corner
                corner = (p0[0], p1[1]) if v0 else (p1[0], p0[1])
                return [p0, corner, p1], "L"
            return [p0] + wps + [p1], ("v" if v0 else "h")
        if d in ("TB", "BT", "LR", "RL") and route != "straight":
            vert = d in ("TB", "BT")
            if vert:
                sep = da.ay + da.h <= db.ay or db.ay + db.h <= da.ay
            else:
                sep = da.ax + da.w <= db.ax or db.ax + db.w <= da.ax
            if not sep:
                vert = not vert  # same rank: connect sideways
            p0, p1 = self._ports(e, a, b, vert, sep)
            if off:
                if vert:
                    p0, p1 = (p0[0] + off, p0[1]), (p1[0] + off, p1[1])
                else:
                    p0, p1 = (p0[0], p0[1] + off), (p1[0], p1[1] + off)
            # boxes overlap on the cross axis: draw one straight line, no jog / double trace
            rect = {"box", "square", "round", "pill", "cylinder", "note", "image", "none"}
            boxy = all(x.attrs.get("shape", "box") in rect or isinstance(x, Group) for x in (a, b))
            if not wps and not off and boxy:
                i = 0 if vert else 1
                lo = max(a.ax if vert else a.ay, b.ax if vert else b.ay)
                hi = min((a.ax + a.w) if vert else (a.ay + a.h), (b.ax + b.w) if vert else (b.ay + b.h))
                if abs(p0[i] - p1[i]) > 0.5 and hi - lo >= 16:
                    m = min(max((p0[i] + p1[i]) / 2, lo + 8), hi - 8)
                    p0 = (m, p0[1]) if vert else (p0[0], m)
                    p1 = (m, p1[1]) if vert else (p1[0], m)
            return [p0] + wps + [p1], ("v" if vert else "h")
        # free layouts: shortest centre-to-centre, clipped to outline
        tgt0 = wps[0] if wps else (b.cx, b.cy)
        tgt1 = wps[-1] if wps else (a.cx, a.cy)
        p0 = boundary_point(a, *tgt0, a.attrs.get("shape", "box"))
        p1 = boundary_point(b, *tgt1, b.attrs.get("shape", "box"))
        return [p0] + wps + [p1], ("v" if abs(p1[1] - p0[1]) >= abs(p1[0] - p0[0]) else "h")

    def path_d(self, pts, axis, route, radius=6.0, stub=None, mid=None):
        if axis == "L":  # explicit-port L shape: polyline with rounded corner
            return self._rounded(list(pts), max(radius, 8))
        if route == "straight" or len(pts) < 2:
            return "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        if route == "bend":
            # straight run in the middle, curved only where it leaves/enters a node
            (x0, y0), (x1, y1) = pts[0], pts[-1]
            span = abs(y1 - y0) if axis == "v" else abs(x1 - x0)
            k = min(stub if stub is not None else radius * 1.5, span / 2)
            sy = math.copysign(k, (y1 - y0) or 1)
            sx = math.copysign(k, (x1 - x0) or 1)
            mid = list(pts[1:-1])
            if axis == "v":
                poly = [pts[0], (x0, y0 + sy)] + mid + [(x1, y1 - sy), pts[-1]]
            else:
                poly = [pts[0], (x0 + sx, y0)] + mid + [(x1 - sx, y1), pts[-1]]
            return self._rounded(poly, radius)
        if route == "ortho":
            seg = [pts[0]]
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                if axis == "v":
                    my = mid if mid is not None and len(pts) == 2 else (y0 + y1) / 2
                    seg += [(x0, my), (x1, my), (x1, y1)]
                else:
                    mx = mid if mid is not None and len(pts) == 2 else (x0 + x1) / 2
                    seg += [(mx, y0), (mx, y1), (x1, y1)]
            # drop duplicate / collinear points and round corners
            clean = [seg[0]]
            for p in seg[1:]:
                if abs(p[0] - clean[-1][0]) > 0.05 or abs(p[1] - clean[-1][1]) > 0.05:
                    clean.append(p)
            return self._rounded(clean, radius)
        # curve: cubic beziers with tangents along the flow axis
        d = f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if axis == "v":
                k = (y1 - y0) / 2
                d += f" C {x0:.1f} {y0 + k:.1f} {x1:.1f} {y1 - k:.1f} {x1:.1f} {y1:.1f}"
            else:
                k = (x1 - x0) / 2
                d += f" C {x0 + k:.1f} {y0:.1f} {x1 - k:.1f} {y1:.1f} {x1:.1f} {y1:.1f}"
        return d

    @staticmethod
    def _rounded(pts, r):
        if len(pts) < 3:
            return "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        d = f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"
        for p0, p1, p2 in zip(pts, pts[1:], pts[2:]):
            v1 = (p1[0] - p0[0], p1[1] - p0[1])
            v2 = (p2[0] - p1[0], p2[1] - p1[1])
            l1, l2 = math.hypot(*v1), math.hypot(*v2)
            rr = min(r, l1 / 2, l2 / 2)
            if l1 == 0 or l2 == 0:
                continue
            a = (p1[0] - v1[0] / l1 * rr, p1[1] - v1[1] / l1 * rr)
            b = (p1[0] + v2[0] / l2 * rr, p1[1] + v2[1] / l2 * rr)
            d += f" L {a[0]:.1f} {a[1]:.1f} Q {p1[0]:.1f} {p1[1]:.1f} {b[0]:.1f} {b[1]:.1f}"
        d += f" L {pts[-1][0]:.1f} {pts[-1][1]:.1f}"
        return d

    def marker(self, head, color, width, start):
        key = f"{head}-{color}-{width}-{'s' if start else 'e'}".replace("#", "")
        mid = "m-" + "".join(ch if ch.isalnum() or ch == "-" else "_" for ch in key)
        if mid in self.defs:
            return mid
        L = HEAD_LEN
        shapes = {
            "triangle": f'<path d="M0,0 L{L},{L/2} L0,{L} z" fill="{color}"/>',
            "open": f'<path d="M0,0 L{L},{L/2} L0,{L}" fill="none" stroke="{color}" stroke-width="1.3"/>',
            "diamond": f'<path d="M0,{L/2} L{L/2},0 L{L},{L/2} L{L/2},{L} z" fill="{color}"/>',
            "dot": f'<circle cx="{L/2}" cy="{L/2}" r="{L/2.4}" fill="{color}"/>',
            "bar": f'<path d="M{L-1},0 L{L-1},{L}" stroke="{color}" stroke-width="2"/>',
        }
        body = shapes.get(head, shapes["triangle"])
        orient = "auto-start-reverse" if start else "auto"
        # markerUnits=userSpaceOnUse keeps heads constant regardless of edge width,
        # scale gently with width instead.
        s = max(1.0, 0.6 + width * 0.35)
        self.defs[mid] = (f'<marker id="{mid}" viewBox="0 0 {L} {L}" refX="{L - 1}" refY="{L/2}" '
                          f'markerWidth="{L*s:.1f}" markerHeight="{L*s:.1f}" markerUnits="userSpaceOnUse" '
                          f'orient="{orient}">{body}</marker>')
        return mid

    def render_edge(self, e: Edge):
        st = e.style
        pts, axis = self.edge_geometry(e)
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
        head = st.get("head", "triangle")
        pts = list(pts)
        tip_end, tip_start = pts[-1], pts[0]
        # head length: explicit CSS/attr `head-size`, else grows gently with width (capped)
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
        if arrow in ("end", "both"):
            d_end = end_dir(tip_end, pts[-2])
            heads.append((tip_end, d_end))
            # stop the stroke at the head's base so nothing pokes through the tip
            pts[-1] = (tip_end[0] - d_end[0] * hl * 0.9, tip_end[1] - d_end[1] * hl * 0.9)
        if arrow in ("start", "both"):
            d_st = end_dir(tip_start, pts[1])
            heads.append((tip_start, d_st))
            pts[0] = (tip_start[0] - d_st[0] * hl * 0.9, tip_start[1] - d_st[1] * hl * 0.9)
        stub = px(st["stub"]) if "stub" in st else None
        if stub is not None and heads:
            stub += hl  # keep the bend clear of the head
        radius = px(st.get("radius"), 12 if route == "bend" else 6)
        cap = "butt" if heads else "round"
        attrs = [f'd="{self.path_d(pts, axis, route, radius, stub, self.bend_level.get(e.id))}"', 'fill="none"', f'stroke="{color}"',
                 f'stroke-width="{width:g}"', f'stroke-linecap="{cap}"', 'stroke-linejoin="round"']
        if dash:
            attrs.append(f'stroke-dasharray="{dash}"')
        cls = " ".join(["nodal-edge"] + e.classes)
        self.out.append(f'<g id="{e.id}" class="{cls}"><path {" ".join(attrs)}/>')
        for tip, dvec in heads:
            self.out.append(self.head_shape(head, tip, dvec, hl, color, width))
        if e.label:
            self.edge_label(e, pts)
        self.out.append("</g>")

    @staticmethod
    def head_shape(kind, tip, d, hl, color, width):
        """Arrowhead as plain geometry: tip sits exactly on the target outline."""
        tx, ty = tip
        ux, uy = d
        nx, ny = -uy, ux
        hw = max(hl * 0.42, width * 1.2)

        def P(a, b):  # a along -d from tip, b along normal
            return f"{tx - ux * a + nx * b:.1f},{ty - uy * a + ny * b:.1f}"
        if kind == "open":
            return (f'<polyline class="nodal-head" points="{P(hl, hw)} {P(0, 0)} {P(hl, -hw)}" fill="none" '
                    f'stroke="{color}" stroke-width="{max(1.2, width * 0.8):g}" stroke-linejoin="miter"/>')
        if kind == "diamond":
            return (f'<polygon class="nodal-head" points="{P(0, 0)} {P(hl / 2, hw)} {P(hl, 0)} {P(hl / 2, -hw)}" '
                    f'fill="{color}"/>')
        if kind == "dot":
            r = hl / 2.2
            return f'<circle class="nodal-head" cx="{tx - ux * r:.1f}" cy="{ty - uy * r:.1f}" r="{r:.1f}" fill="{color}"/>'
        if kind == "bar":
            return (f'<line class="nodal-head" x1="{tx + nx * hw:.1f}" y1="{ty + ny * hw:.1f}" '
                    f'x2="{tx - nx * hw:.1f}" y2="{ty - ny * hw:.1f}" stroke="{color}" stroke-width="{max(2, width):g}"/>')
        return f'<polygon class="nodal-head" points="{P(0, 0)} {P(hl, hw)} {P(hl, -hw)}" fill="{color}"/>'

    @staticmethod
    def _pull(p, toward, dist):
        if dist == 0:
            return p
        dx, dy = toward[0] - p[0], toward[1] - p[1]
        l = math.hypot(dx, dy) or 1
        return (p[0] + dx / l * dist, p[1] + dy / l * dist)

    def edge_label(self, e, pts):
        from .text import measure
        st = e.style
        fs = px(st.get("font-size"), 11)
        w, h, lines = measure(e.label, st.get("font-family", "sans-serif"), fs)
        if len(pts) % 2 == 0:
            i = len(pts) // 2
            mx = (pts[i - 1][0] + pts[i][0]) / 2
            my = (pts[i - 1][1] + pts[i][1]) / 2
        else:
            mx, my = pts[len(pts) // 2]
        bg = st.get("background", self.doc.root.style.get("background", "#ffffff"))
        self.out.append(f'<rect x="{mx - w/2 - 3:.1f}" y="{my - h/2 - 1:.1f}" width="{w + 6:.1f}" '
                        f'height="{h + 2:.1f}" rx="3" fill="{bg}" fill-opacity="0.9"/>')
        self.text(lines, mx, my - h / 2, fs, st, "middle")

    # ------------------------------------------------------------ boxes
    def text(self, lines, cx, top, fs, st, anchor="middle"):
        color = st.get("color", "#111827")
        fam = st.get("font-family", "sans-serif")
        weight = st.get("font-weight", "normal")
        italic = st.get("font-style", "normal")
        lh = fs * 1.25
        for i, line in enumerate(lines):
            y = top + lh * i + fs * 0.95
            self.out.append(f'<text x="{cx:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
                            f'font-family={quoteattr(fam)} font-size="{fs:g}" font-weight="{weight}" '
                            f'font-style="{italic}" fill="{color}">{escape(line)}</text>')

    def shape(self, n, shape, st, cls):
        x, y, w, h = n.ax, n.ay, n.w, n.h
        fill = st.get("fill", "#fff")
        stroke = st.get("stroke", "none")
        sw = px(st.get("stroke-width"), 1)
        common = f'fill="{fill}" stroke="{stroke}" stroke-width="{sw:g}"'
        if st.get("stroke-dasharray"):
            common += f' stroke-dasharray="{st["stroke-dasharray"]}"'
        if st.get("opacity"):
            common += f' opacity="{st["opacity"]}"'
        if st.get("shadow") == "soft":
            common += ' filter="url(#nodal-shadow)"'
            self.defs["nodal-shadow"] = ('<filter id="nodal-shadow" x="-20%" y="-20%" width="140%" height="150%">'
                                         '<feDropShadow dx="0" dy="2" stdDeviation="2.5" flood-opacity="0.18"/></filter>')
        r = px(st.get("border-radius"), 0)
        if shape == "round":
            r = max(r, 10)
        if shape == "pill":
            r = h / 2
        if shape in ("box", "round", "pill", "note", "square"):
            return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r:g}" {common}/>'
        if shape in ("circle", "ellipse"):
            return f'<ellipse cx="{n.cx:.1f}" cy="{n.cy:.1f}" rx="{w/2:.1f}" ry="{h/2:.1f}" {common}/>'
        if shape == "diamond":
            p = f"{n.cx:.1f},{y:.1f} {x+w:.1f},{n.cy:.1f} {n.cx:.1f},{y+h:.1f} {x:.1f},{n.cy:.1f}"
            return f'<polygon points="{p}" {common}/>'
        if shape == "hexagon":
            k = h / 2 * 0.6
            p = f"{x+k:.1f},{y:.1f} {x+w-k:.1f},{y:.1f} {x+w:.1f},{n.cy:.1f} {x+w-k:.1f},{y+h:.1f} {x+k:.1f},{y+h:.1f} {x:.1f},{n.cy:.1f}"
            return f'<polygon points="{p}" {common}/>'
        if shape == "cylinder":
            e = 6
            return (f'<path d="M{x:.1f},{y+e:.1f} A{w/2:.1f},{e} 0 0 1 {x+w:.1f},{y+e:.1f} V{y+h-e:.1f} '
                    f'A{w/2:.1f},{e} 0 0 1 {x:.1f},{y+h-e:.1f} Z" {common}/>'
                    f'<path d="M{x:.1f},{y+e:.1f} A{w/2:.1f},{e} 0 0 0 {x+w:.1f},{y+e:.1f}" fill="none" '
                    f'stroke="{stroke}" stroke-width="{sw:g}"/>')
        return ""

    def render_node(self, n: Node):
        st = n.style
        shape = n.attrs.get("shape", "box")
        cls = " ".join(["nodal-node"] + n.classes)
        self.out.append(f'<g id={quoteattr(n.id)} class="{cls}">')
        self.out.append(self.shape(n, shape, st, cls))
        fs = px(st.get("font-size"), 14)
        if n.image:
            img = n.image
            pt, pr, pb, pl = box4(st.get("padding"), 8) if shape != "image" else (0, 0, 0, 0)
            ix = n.cx - img["dw"] / 2
            gap = 4 if n.text_lines else 0
            block = img["dh"] + gap + n.text_h
            iy = n.ay + (n.h - block) / 2 if shape != "image" else n.ay
            self.out.append(f'<image x="{ix:.1f}" y="{iy:.1f}" width="{img["dw"]:.1f}" height="{img["dh"]:.1f}" '
                            f'href="{img["href"]}" xlink:href="{img["href"]}" preserveAspectRatio="xMidYMid meet"/>')
            self.text(n.text_lines, n.cx, iy + img["dh"] + gap, fs, st)
        else:
            self.text(n.text_lines, n.cx, n.cy - n.text_h / 2, fs, st)
        self.out.append("</g>")

    def render_group(self, g: Group):
        st = g.style
        cls = " ".join(["nodal-group"] + g.classes)
        self.out.append(f'<g id={quoteattr(g.id)} class="{cls}">')
        self.out.append(self.shape(g, g.attrs.get("shape", "box"), st, cls))
        if g.label:
            fs = px(st.get("font-size"), 12)
            pt, pr, pb, pl = box4(st.get("padding"), 14)
            lines = g.label.split("\n")
            align = st.get("text-align", "left")
            if align == "center":
                x, anchor = g.cx, "middle"
            elif align == "right":
                x, anchor = g.ax + g.w - pr, "end"
            else:
                x, anchor = g.ax + pl, "start"
            top = g.ay + pt if st.get("label-position", "top") != "bottom" else g.ay + g.h - pb - g.label_h + 6
            self.text(lines, x, top, fs, st, anchor)
        for c in g.children:
            if isinstance(c, Group):
                self.render_group(c)
        self.out.append("</g>")

    def render(self) -> str:
        root = self.doc.root
        pad = box4(root.style.get("padding"), 16)
        # groups first, then edges, then nodes (edges sit below nodes, above groups)
        body_groups, body_nodes = [], []
        self.out = body_groups
        for c in root.children:
            if isinstance(c, Group):
                self.render_group(c)
        self.out = edges_out = []
        self.prepare_edges()
        self._shared_bends()
        for e in self.doc.edges:
            self.render_edge(e)
        self.out = body_nodes
        for c in self.doc.walk():
            if isinstance(c, Node):
                self.render_node(c)
        W = root.w - box4(root.style.get("padding"), 16)[1] - box4(root.style.get("padding"), 16)[3]
        _ = W
        w, h = root.w, root.h
        bg = root.style.get("background")
        head = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'width="{w:.0f}" height="{h:.0f}" viewBox="0 0 {w:.1f} {h:.1f}" class="nodal">']
        if self.defs:
            head.append("<defs>" + "".join(self.defs.values()) + "</defs>")
        if bg:
            head.append(f'<rect width="100%" height="100%" fill="{bg}"/>')
        _ = pad
        return "\n".join(head + body_groups + edges_out + body_nodes + ["</svg>"]) + "\n"


def render_svg(doc: Document) -> str:
    return SvgRenderer(doc).render()
