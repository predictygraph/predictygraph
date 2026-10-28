"""Edge routing (format-independent): ports, lanes, bus levels and octilinear paths.

The router works on the laid-out AST and decides *where* every edge goes. It reports
`needs` back to the layout when a channel between two ranks is too narrow for the lanes
that have to pass through it; the pipeline then widens that gap and routes again.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .layout import direct_child
from .model import Document, Edge, Group
from .style import px

LANE = 9.0    # distance between parallel lanes
CLEAR = 12.0  # min distance between a horizontal run and the boxes above/below it
RECT_SHAPES = {"box", "square", "round", "pill", "cylinder", "note", "image", "none"}


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


@dataclass
class Diagonal:
    """When may a bend/ortho jog be a slant instead of a right-angle step?"""
    mode: str = "auto"
    max: float = 40.0
    angle: float = 45.0

    @classmethod
    def from_style(cls, st: dict, route: str) -> "Diagonal":
        dg = str(st.get("diagonal", "40" if route == "bend" else "0")).strip()
        fixed = {"none": 0.0, "always": 1e9}
        return cls("legacy" if dg == "legacy" else "auto",
                   fixed[dg] if dg in fixed else px(dg, 40.0),
                   min(80.0, max(10.0, px(st.get("diagonal-angle"), 45.0))))


def octilinear(p0, p1, axis, mid, stub, diag: Diagonal):
    """Route between two ports with horizontal/vertical runs and at most one diagonal.

    main  = distance along the flow axis, cross = sideways offset to make up.
    * cross ~ 0                     -> one straight line
    * cross <= diag.max and the slant fits between the stubs -> stub, slant, stub
    * otherwise                     -> stub, perpendicular run, stub (Z shape)
    The jog is centred on `mid` (lane / channel level) if given.
    """
    (x0, y0), (x1, y1) = p0, p1
    v = axis == "v"
    a0, a1 = (y0, y1) if v else (x0, x1)      # main axis
    c0, c1 = (x0, x1) if v else (y0, y1)      # cross axis
    main, cross = a1 - a0, c1 - c0
    sgn = 1.0 if main >= 0 else -1.0

    def P(a, c):
        return (c, a) if v else (a, c)

    if abs(cross) < 0.5:
        return [p0, p1]
    angle = diag.angle
    stub = min(stub, abs(main) / 2)
    if mid is not None:  # a lane/channel level wins over the default stub length
        stub = max(2.0, min(stub, abs(mid - a0), abs(a1 - mid)))
    room = abs(main) - 2 * stub
    if diag.max >= 1e9 and room > 1:  # diagonal=always: steepen until the slant fits
        angle = max(angle, math.degrees(math.atan2(abs(cross), room)))
    dlen = abs(cross) / math.tan(math.radians(angle))  # main-axis length the slant uses
    centre = mid if mid is not None else (a0 + a1) / 2
    if abs(cross) <= diag.max and dlen <= room:
        if sgn > 0:
            s = max(a0 + stub, min(centre - dlen / 2, a1 - (stub + dlen)))
        else:
            s = min(a0 - stub, max(centre + dlen / 2, a1 + (stub + dlen)))
        return [p0, P(s, c0), P(s + sgn * dlen, c1), p1]
    if sgn > 0:
        m = max(a0 + stub, min(centre, a1 - stub))
    else:
        m = min(a0 - stub, max(centre, a1 + stub))
    return [p0, P(m, c0), P(m, c1), p1]


def rounded(pts, r):
    """Polyline -> path segments with rounded corners (quadratic)."""
    if len(pts) < 3:
        return [("M", *pts[0])] + [("L", *p) for p in pts[1:]]
    segs = [("M", *pts[0])]
    for p0, p1, p2 in zip(pts, pts[1:], pts[2:]):
        v1 = (p1[0] - p0[0], p1[1] - p0[1])
        v2 = (p2[0] - p1[0], p2[1] - p1[1])
        l1, l2 = math.hypot(*v1), math.hypot(*v2)
        if l1 == 0 or l2 == 0:
            continue
        rr = min(r, l1 / 2, l2 / 2)
        a = (p1[0] - v1[0] / l1 * rr, p1[1] - v1[1] / l1 * rr)
        b = (p1[0] + v2[0] / l2 * rr, p1[1] + v2[1] / l2 * rr)
        segs += [("L", *a), ("Q", *p1, *b)]
    segs.append(("L", *pts[-1]))
    return segs


class Router:
    def __init__(self, doc: Document):
        self.doc = doc
        self.offset: dict[str, float] = {}
        self.port_shift: dict[tuple[str, int], float] = {}
        self.bend_level: dict[str, float] = {}
        self.channel: dict[str, tuple[float, float]] = {}
        self.gapkey: dict[str, tuple[str, int]] = {}
        self.needs: dict[tuple[str, int], float] = {}

    def route(self) -> "Router":
        self._parallel_offsets()
        self._spread_ports()
        self._shared_bends()
        self._separate_channels()
        return self

    def level(self, e: Edge) -> float | None:
        """Where the sideways jog of `e` sits on the flow axis."""
        if e.id in self.bend_level:
            return self.bend_level[e.id]
        ch = self.channel.get(e.id)
        return (ch[0] + ch[1]) / 2 if ch else None

    # ------------------------------------------------------------ passes
    def _parallel_offsets(self):
        pairs: dict[tuple[str, str], list[Edge]] = {}
        for e in self.doc.edges:
            pairs.setdefault(tuple(sorted((e.src, e.dst))), []).append(e)
        for es in pairs.values():
            n = len(es)
            for i, e in enumerate(es):
                k = (i - (n - 1) / 2) * 12
                # opposite-direction edges get mirrored sign so they stay apart
                self.offset[e.id] = k if e.src <= e.dst else -k

    def _spread_ports(self):
        """Several curved/bent edges on one side of a node: spread them symmetrically
        around the side's middle (ordered by where they go)."""
        sides: dict[tuple[str, str], list] = {}
        for e in self.doc.edges:
            if e.attrs.get("exit") or e.attrs.get("enter") or self.offset.get(e.id):
                continue
            pts, axis = self.geometry(e)
            if axis not in ("v", "h"):
                continue
            a, b = self.doc.items[e.src], self.doc.items[e.dst]
            if flow_dir(lca(a, b, self.doc.root)) == "auto" or e.style.get("route", "curve") in ("straight", "ortho"):
                continue  # ortho fan-in/out merges into a bus instead
            i = 0 if axis == "v" else 1
            for end, node, here, there in ((0, a, pts[0], pts[1] if len(pts) > 2 else pts[-1]),
                                           (1, b, pts[-1], pts[-2] if len(pts) > 2 else pts[0])):
                side = ("bottom" if there[1] > here[1] else "top") if axis == "v" else \
                       ("right" if there[0] > here[0] else "left")
                sides.setdefault((node.id, side), []).append((there[i], e.id, end))
        for (nid, side), lst in sides.items():
            if len(lst) < 2:
                continue
            n = self.doc.items[nid]
            if n.attrs.get("shape", "box") in ("diamond", "circle", "ellipse") and not isinstance(n, Group):
                continue
            span = n.w if side in ("top", "bottom") else n.h
            step = min(18.0, (span - 12) / (len(lst) - 1)) if span > 12 else 0.0
            lst.sort()
            for k, (_, eid, end) in enumerate(lst):
                self.port_shift[(eid, end)] = (k - (len(lst) - 1) / 2) * step

    def _shared_bends(self):
        """Ortho fan-in/fan-out: edges sharing a target (or source) turn at one common
        level, so they merge into a single bus line (class-diagram style)."""
        geo = {e.id: self.geometry(e) for e in self.doc.edges if e.style.get("route", "curve") == "ortho"}
        for key in ("dst", "src"):
            buckets: dict[str, list] = {}
            for e in self.doc.edges:
                if e.id in geo and geo[e.id][1] in ("v", "h") and len(geo[e.id][0]) == 2:
                    buckets.setdefault(getattr(e, key), []).append(e)
            for es in buckets.values():
                if len(es) < 2 or any(e.id in self.bend_level for e in es):
                    continue
                axis = geo[es[0].id][1]
                i = 1 if axis == "v" else 0
                hub = [geo[e.id][0][-1 if key == "dst" else 0][i] for e in es]
                far = [geo[e.id][0][0 if key == "dst" else -1][i] for e in es]
                if len({round(h) for h in hub}) != 1 or len({geo[e.id][1] for e in es}) != 1:
                    continue
                chans = {self.channel.get(e.id) for e in es}
                if len(chans) == 1 and None not in chans:
                    lo, hi = chans.pop()
                    level = (lo + hi) / 2
                else:
                    h = hub[0]
                    nearest = min(far, key=lambda f: abs(f - h))
                    level = h + (nearest - h) / 2
                for e in es:
                    self.bend_level[e.id] = level

    def _separate_channels(self):
        """Distinct edges whose sideways runs land on the same level and overlap get their
        own lanes. Edges sharing a source or target *and* the same look stay merged (bus).
        Channels too narrow for their lanes are reported in `self.needs`."""
        runs = []
        for e in self.doc.edges:
            if e.style.get("route", "curve") not in ("bend", "ortho") or e.attrs.get("exit") or e.attrs.get("enter"):
                continue
            pts, axis = self.geometry(e)
            if axis not in ("v", "h") or len(pts) != 2:
                continue
            (x0, y0), (x1, y1) = pts
            v = axis == "v"
            a0, a1 = (y0, y1) if v else (x0, x1)
            c0, c1 = (x0, x1) if v else (y0, y1)
            if abs(c1 - c0) < 0.5:
                continue
            lvl = self.level(e)
            runs.append({"e": e, "axis": axis, "level": (a0 + a1) / 2 if lvl is None else lvl,
                         "lo": min(c0, c1), "hi": max(c0, c1), "c0": c0, "c1": c1, "a0": a0, "a1": a1})
        lanes_at: dict[tuple[str, int], int] = {}
        for r in runs:
            gk = self.gapkey.get(r["e"].id)
            if gk:
                lanes_at[gk] = max(lanes_at.get(gk, 0), 1)

        def look(ed):
            return (ed.body, ed.style.get("stroke-dasharray"), ed.style.get("stroke"), tuple(sorted(ed.classes)))

        runs.sort(key=lambda r: (r["axis"], r["level"]))
        used: set[int] = set()
        for i, r in enumerate(runs):
            if i in used:
                continue
            cl = [i]
            for j in range(i + 1, len(runs)):
                s = runs[j]
                if j in used or s["axis"] != r["axis"] or abs(s["level"] - r["level"]) > LANE:
                    continue
                if any(min(s["hi"], runs[k]["hi"]) - max(s["lo"], runs[k]["lo"]) > 1 for k in cl):
                    cl.append(j)
            if len(cl) < 2:
                continue
            lanes: list[list[int]] = []
            for k in cl:
                ek = runs[k]["e"]
                for ln in lanes:
                    if any((runs[m]["e"].src == ek.src or runs[m]["e"].dst == ek.dst)
                           and look(runs[m]["e"]) == look(ek) for m in ln):
                        ln.append(k)
                        break
                else:
                    lanes.append([k])
            if len(lanes) < 2:
                continue
            used.update(cl)
            # order lanes so runs don't cross: the run that starts further along its
            # travel direction turns later (further from the source rank)
            lanes.sort(key=lambda ln: sum(runs[m]["c0"] - runs[m]["c1"] for m in ln) / len(ln))
            base = sum(runs[m]["level"] for m in cl) / len(cl)
            n = len(lanes)
            for idx, ln in enumerate(lanes):
                lvl = base + (idx - (n - 1) / 2) * LANE
                for m in ln:
                    rr = runs[m]
                    eid = rr["e"].id
                    ch = self.channel.get(eid)
                    if ch and ch[1] - ch[0] >= 2 * CLEAR:
                        lvl_c = min(max(lvl, ch[0] + CLEAR), ch[1] - CLEAR)
                    else:
                        lo_a, hi_a = sorted((rr["a0"], rr["a1"]))
                        lvl_c = min(max(lvl, lo_a + 4), hi_a - 4)
                    self.bend_level[eid] = lvl_c
                    gk = self.gapkey.get(eid)
                    if gk:
                        lanes_at[gk] = max(lanes_at[gk], n)
        # report channels that are too narrow for the lanes they carry
        for e in self.doc.edges:
            gk = self.gapkey.get(e.id)
            if not gk or gk not in lanes_at:
                continue
            lo, hi = self.channel[e.id]
            need = (lanes_at[gk] - 1) * LANE + 2 * CLEAR - (hi - lo)
            if need > 0.5:
                self.needs[gk] = max(self.needs.get(gk, 0.0), need)

    # ------------------------------------------------------------ geometry
    def _ports(self, a, b, vert):
        if vert:
            down = b.cy > a.cy
            return port(a, "bottom" if down else "top"), port(b, "top" if down else "bottom")
        right = b.cx > a.cx
        return port(a, "right" if right else "left"), port(b, "left" if right else "right")

    def _record_channel(self, e, owner, da, db, vert):
        """Free band between the two outer boxes on the flow axis (where runs belong)."""
        if vert:
            lo, hi = (da.ay + da.h, db.ay) if db.ay >= da.ay + da.h else (db.ay + db.h, da.ay)
        else:
            lo, hi = (da.ax + da.w, db.ax) if db.ax >= da.ax + da.w else (db.ax + db.w, da.ax)
        self.channel[e.id] = (lo, hi)
        ri = getattr(getattr(owner, "layout_obj", None), "rank_index", {})
        if da.id in ri and db.id in ri and abs(ri[da.id] - ri[db.id]) == 1:
            self.gapkey[e.id] = (owner.id, min(ri[da.id], ri[db.id]))

    def geometry(self, e: Edge):
        """-> (points, axis). axis: v | h (flow axis), L (explicit L port) or free."""
        a, b = self.doc.items[e.src], self.doc.items[e.dst]
        owner = lca(a, b, self.doc.root)
        da, db = direct_child(a, owner), direct_child(b, owner)
        d = flow_dir(owner)
        route = e.style.get("route", "curve")
        wps = list(e.waypoints)
        off = self.offset.get(e.id, 0.0)
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
            elif not wps:
                self._record_channel(e, owner, da, db, vert)
            p0, p1 = self._ports(a, b, vert)
            s0, s1 = self.port_shift.get((e.id, 0), 0.0), self.port_shift.get((e.id, 1), 0.0)
            if vert:
                p0, p1 = (p0[0] + s0, p0[1]), (p1[0] + s1, p1[1])
            else:
                p0, p1 = (p0[0], p0[1] + s0), (p1[0], p1[1] + s1)
            if s0 or s1:
                return [p0] + wps + [p1], ("v" if vert else "h")
            if off:
                if vert:
                    p0, p1 = (p0[0] + off, p0[1]), (p1[0] + off, p1[1])
                else:
                    p0, p1 = (p0[0], p0[1] + off), (p1[0], p1[1] + off)
            # boxes overlap on the cross axis: one straight line, no jog / double trace
            boxy = all(x.attrs.get("shape", "box") in RECT_SHAPES or isinstance(x, Group) for x in (a, b))
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

    # ------------------------------------------------------------ paths
    def polyline(self, pts, axis, route, radius, stub, mid, diag: Diagonal):
        """Corner points of the drawn path (curves: just the anchor points)."""
        if axis == "L" or route == "straight" or len(pts) < 2:
            return list(pts)
        if route in ("bend", "ortho") and len(pts) == 2 and diag.mode != "legacy":
            return octilinear(pts[0], pts[-1], axis, mid, stub if stub is not None else radius * 1.5, diag)
        if route == "bend":
            (x0, y0), (x1, y1) = pts[0], pts[-1]
            span = abs(y1 - y0) if axis == "v" else abs(x1 - x0)
            k = min(stub if stub is not None else radius * 1.5, span / 2)
            sy = math.copysign(k, (y1 - y0) or 1)
            sx = math.copysign(k, (x1 - x0) or 1)
            inner = list(pts[1:-1])
            if axis == "v":
                return [pts[0], (x0, y0 + sy)] + inner + [(x1, y1 - sy), pts[-1]]
            return [pts[0], (x0 + sx, y0)] + inner + [(x1 - sx, y1), pts[-1]]
        if route == "ortho":
            seg = [pts[0]]
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                if axis == "v":
                    my = mid if mid is not None and len(pts) == 2 else (y0 + y1) / 2
                    seg += [(x0, my), (x1, my), (x1, y1)]
                else:
                    mx = mid if mid is not None and len(pts) == 2 else (x0 + x1) / 2
                    seg += [(mx, y0), (mx, y1), (x1, y1)]
            clean = [seg[0]]
            for p in seg[1:]:
                if abs(p[0] - clean[-1][0]) > 0.05 or abs(p[1] - clean[-1][1]) > 0.05:
                    clean.append(p)
            return clean
        return list(pts)

    def path_segs(self, pts, axis, route, radius, stub, mid, diag: Diagonal):
        if axis == "L":
            return rounded(list(pts), max(radius, 8))
        if route == "straight" or len(pts) < 2:
            return rounded(list(pts), 0)
        if route in ("bend", "ortho"):
            return rounded(self.polyline(pts, axis, route, radius, stub, mid, diag), radius)
        # curve: cubic beziers with tangents along the flow axis
        segs = [("M", *pts[0])]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if axis == "v":
                k = (y1 - y0) / 2
                segs.append(("C", x0, y0 + k, x1, y1 - k, x1, y1))
            else:
                k = (x1 - x0) / 2
                segs.append(("C", x0 + k, y0, x1 - k, y1, x1, y1))
        return segs
