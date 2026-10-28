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
    def edge_geometry(self, e: Edge):
        a, b = self.doc.items[e.src], self.doc.items[e.dst]
        owner = lca(a, b, self.doc.root)
        da, db = direct_child(a, owner), direct_child(b, owner)
        d = flow_dir(owner)
        route = e.style.get("route", "curve")
        wps = list(e.waypoints)
        if d in ("TB", "BT", "LR", "RL") and route != "straight":
            vert = d in ("TB", "BT")
            # are the projected boxes separated on the main axis?
            if vert:
                sep = da.ay + da.h <= db.ay or db.ay + db.h <= da.ay
            else:
                sep = da.ax + da.w <= db.ax or db.ax + db.w <= da.ax
            if sep:
                if vert:
                    down = b.cy > a.cy
                    p0 = port(a, "bottom" if down else "top")
                    p1 = port(b, "top" if down else "bottom")
                else:
                    right = b.cx > a.cx
                    p0 = port(a, "right" if right else "left")
                    p1 = port(b, "left" if right else "right")
                return [p0] + wps + [p1], ("v" if vert else "h")
            # same rank: connect sideways in the cross direction
            if vert:
                right = b.cx > a.cx
                return [port(a, "right" if right else "left"), port(b, "left" if right else "right")], "h"
            down = b.cy > a.cy
            return [port(a, "bottom" if down else "top"), port(b, "top" if down else "bottom")], "v"
        # free layouts: shortest centre-to-centre, clipped to outline
        tgt0 = wps[0] if wps else (b.cx, b.cy)
        tgt1 = wps[-1] if wps else (a.cx, a.cy)
        p0 = boundary_point(a, *tgt0, a.attrs.get("shape", "box"))
        p1 = boundary_point(b, *tgt1, b.attrs.get("shape", "box"))
        return [p0] + wps + [p1], ("v" if abs(p1[1] - p0[1]) >= abs(p1[0] - p0[0]) else "h")

    def path_d(self, pts, axis, route, radius=6.0, stub=None):
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
                    my = (y0 + y1) / 2
                    seg += [(x0, my), (x1, my), (x1, y1)]
                else:
                    mx = (x0 + x1) / 2
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
        # shorten line under heads so the stroke doesn't poke through
        s = max(1.0, 0.6 + width * 0.35)
        pts = list(pts)
        if arrow in ("end", "both"):
            pts[-1] = self._pull(pts[-1], pts[-2], 0)
        stub = px(st["stub"]) if "stub" in st else None
        attrs = [f'd="{self.path_d(pts, axis, route, px(st.get("radius"), 12 if route == "bend" else 6), stub)}"', 'fill="none"', f'stroke="{color}"',
                 f'stroke-width="{width:g}"', 'stroke-linecap="round"', 'stroke-linejoin="round"']
        if dash:
            attrs.append(f'stroke-dasharray="{dash}"')
        if arrow in ("end", "both"):
            attrs.append(f'marker-end="url(#{self.marker(head, color, width, False)})"')
        if arrow in ("start", "both"):
            attrs.append(f'marker-start="url(#{self.marker(head, color, width, True)})"')
        _ = s
        cls = " ".join(["nodal-edge"] + e.classes)
        self.out.append(f'<g id="{e.id}" class="{cls}"><path {" ".join(attrs)}/>')
        if e.label:
            self.edge_label(e, pts)
        self.out.append("</g>")

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
