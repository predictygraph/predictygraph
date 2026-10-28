"""Hierarchical layout: each container is laid out independently (inside-out)
with its own balancing style, then treated as a single box by its parent."""
from __future__ import annotations

from collections import defaultdict

from .model import Document, Group, Item, Node
from .style import box4, px
from .text import load_image, measure


# ---------------------------------------------------------------- sizing
def size_node(n: Node, doc: Document) -> None:
    st = n.style
    fs = px(st.get("font-size"), 14)
    bold = st.get("font-weight", "normal") in ("bold", "600", "700", "800", "900")
    label = n.label if n.label is not None else n.id
    n.text_w, n.text_h, n.text_lines = measure(label, st.get("font-family", "sans-serif"), fs, bold)
    pt, pr, pb, pl = box4(st.get("padding"), 8)
    shape = n.attrs.get("shape")
    if "image" in n.attrs:
        img = load_image(n.attrs["image"], doc.base_dir)
        iw, ih = img["w"], img["h"]
        if "img-width" in n.attrs or "img-height" in n.attrs:
            tw, th = px(n.attrs.get("img-width"), 0), px(n.attrs.get("img-height"), 0)
            if tw and th:
                iw, ih = tw, th
            elif tw:
                iw, ih = tw, ih * tw / iw
            else:
                iw, ih = iw * th / ih, th
        else:
            s = min(1.0, 96 / max(iw, ih))
            iw, ih = iw * s, ih * s
        img["dw"], img["dh"] = iw, ih
        n.image = img
        shape = shape or "image"
        gap = 4 if n.text_lines else 0
        if shape == "image":
            n.w = max(iw, n.text_w)
            n.h = ih + gap + n.text_h
        else:
            n.w = max(iw, n.text_w) + pl + pr
            n.h = ih + gap + n.text_h + pt + pb
    else:
        shape = shape or "box"
        n.w = n.text_w + pl + pr
        n.h = n.text_h + pt + pb
        if shape in ("circle",):
            d = max(n.text_w, n.text_h) + max(pl, pt) * 1.2
            n.w = n.h = d
        elif shape in ("ellipse",):
            n.w, n.h = n.w * 1.25, n.h * 1.3
        elif shape == "diamond":
            n.w, n.h = n.w * 1.6, n.h * 1.7
        elif shape == "hexagon":
            n.w += n.h * 0.6
        elif shape == "cylinder":
            n.h += 12
    n.attrs["shape"] = shape
    n.w = max(n.w, px(st.get("min-width"), 0), px(n.attrs.get("width"), 0))
    n.h = max(n.h, px(st.get("min-height"), 0), px(n.attrs.get("height"), 0))


# ---------------------------------------------------------------- helpers
def direct_child(item: Item, g: Group) -> Item | None:
    """Ancestor-or-self of `item` that is a direct child of g."""
    cur = item
    while cur is not None and cur.parent is not g:
        cur = cur.parent
    return cur


def local_edges(g: Group, doc: Document):
    """Edges projected onto g's direct children: list of (src_child, dst_child, edge)."""
    out = []
    for e in doc.edges:
        if e.attrs.get("constraint") == "false":
            continue
        a = direct_child(doc.items[e.src], g)
        b = direct_child(doc.items[e.dst], g)
        if a is not None and b is not None and a is not b:
            out.append((a, b, e))
    return out


def opt(g: Group, key: str, default: str) -> str:
    return g.attrs.get(key, default)


# ---------------------------------------------------------------- layouts
class Layout:
    def __init__(self, g: Group, doc: Document):
        self.g, self.doc = g, doc
        self.kids = g.children

    def run(self) -> tuple[float, float]:
        raise NotImplementedError


class LineLayout(Layout):
    """row / column: single line with alignment."""

    def run(self):
        horizontal = opt(self.g, "layout", "row") == "row"
        gap = px(opt(self.g, "gap", "24"))
        align = opt(self.g, "align", "center")
        cross = max((k.h if horizontal else k.w) for k in self.kids)
        pos = 0.0
        for k in self.kids:
            size_c = k.h if horizontal else k.w
            off = {"start": 0, "end": cross - size_c}.get(align, (cross - size_c) / 2)
            if horizontal:
                k.x, k.y = pos, off
                pos += k.w + gap
            else:
                k.x, k.y = off, pos
                pos += k.h + gap
        pos -= gap
        return (pos, cross) if horizontal else (cross, pos)


class GridLayout(Layout):
    def run(self):
        n = len(self.kids)
        if "rows" in self.g.attrs and "cols" not in self.g.attrs:
            rows = int(self.g.attrs["rows"])
            cols = -(-n // rows)
        else:
            cols = int(opt(self.g, "cols", str(max(1, round(n ** 0.5)))))
        gap = px(opt(self.g, "gap", "24"))
        align = opt(self.g, "align", "center")
        slots, taken, auto = {}, set(), []
        for k in self.kids:
            if "row" in k.attrs and "col" in k.attrs:
                rc = (int(k.attrs["row"]), int(k.attrs["col"]))
                slots[k.id] = rc
                taken.add(rc)
            else:
                auto.append(k)
        i = 0
        for k in auto:
            while (i // cols, i % cols) in taken:
                i += 1
            slots[k.id] = (i // cols, i % cols)
            i += 1
        nrows = max(r for r, _ in slots.values()) + 1
        ncols = max(c for _, c in slots.values()) + 1
        if opt(self.g, "uniform", "true") == "true":
            cw = [max(k.w for k in self.kids)] * ncols
            rh = [max(k.h for k in self.kids)] * nrows
        else:
            cw, rh = [0.0] * ncols, [0.0] * nrows
            for k in self.kids:
                r, c = slots[k.id]
                cw[c], rh[r] = max(cw[c], k.w), max(rh[r], k.h)
        xs = [sum(cw[:c]) + gap * c for c in range(ncols)]
        ys = [sum(rh[:r]) + gap * r for r in range(nrows)]
        for k in self.kids:
            r, c = slots[k.id]
            fx = {"start": 0, "end": cw[c] - k.w}.get(align, (cw[c] - k.w) / 2)
            fy = (rh[r] - k.h) / 2
            k.x, k.y = xs[c] + fx, ys[r] + fy
        return xs[-1] + cw[-1], ys[-1] + rh[-1]


class FixedLayout(Layout):
    def run(self):
        for k in self.kids:
            x, y = (k.attrs.get("at", "0,0").split(",") + ["0"])[:2]
            k.x, k.y = float(x), float(y)
        return max(k.x + k.w for k in self.kids), max(k.y + k.h for k in self.kids)


class RadialLayout(Layout):
    def run(self):
        import math
        cid = opt(self.g, "center", self.kids[0].id)
        center = next((k for k in self.kids if k.id == cid), self.kids[0])
        ring = [k for k in self.kids if k is not center]
        biggest = max((max(k.w, k.h) for k in ring), default=0)
        circumference_need = sum(max(k.w, k.h) + 20 for k in ring)
        r_auto = max(circumference_need / (2 * math.pi),
                     max(center.w, center.h) / 2 + max((min(k.w, k.h) for k in ring), default=0) / 2 + 36)
        start = math.radians(px(opt(self.g, "start-angle", "-90"), -90))
        angles = [start + 2 * math.pi * i / max(1, len(ring)) for i in range(len(ring))]

        def support(k, a):  # half-extent of a box along direction a
            return abs(math.cos(a)) * k.w / 2 + abs(math.sin(a)) * k.h / 2
        if ring:
            r_auto = max(r_auto, max(support(center, a) + support(k, a) + 24 for k, a in zip(ring, angles)))
        r = px(opt(self.g, "radius", "auto"), 0) or r_auto
        pts = []
        for k, a in zip(ring, angles):
            pts.append((k, r * math.cos(a), r * math.sin(a)))
        pts.append((center, 0.0, 0.0))
        minx = min(px_ - k.w / 2 for k, px_, _ in pts)
        miny = min(py - k.h / 2 for k, _, py in pts)
        for k, cx, cy in pts:
            k.x, k.y = cx - k.w / 2 - minx, cy - k.h / 2 - miny
        return (max(k.x + k.w for k, _, _ in pts), max(k.y + k.h for k, _, _ in pts))


class LayeredLayout(Layout):
    """Sugiyama-style: ranking, (optional) crossing reduction, balancing."""

    def run(self):
        g = self.g
        d = opt(g, "dir", "TB").upper()
        horizontal = d in ("LR", "RL")
        rank_gap = px(opt(g, "rank-gap", "56"))
        node_gap = px(opt(g, "node-gap", "28"))
        balance = opt(g, "balance", "median")
        order_mode = opt(g, "order", "auto")
        kids = self.kids
        idx = {k.id: i for i, k in enumerate(kids)}
        edges = [(a.id, b.id, float(e.attrs.get("weight", 1))) for a, b, e in local_edges(g, self.doc)]

        # 1. break cycles with DFS in source order
        succ = defaultdict(list)
        for a, b, w in edges:
            succ[a].append((b, w))
        state, dag = {}, []

        def dfs(u):
            state[u] = 1
            for v, w in succ[u]:
                if state.get(v) == 1:
                    dag.append((v, u, w))  # reverse back edge
                else:
                    dag.append((u, v, w))
                    if v not in state:
                        dfs(v)
            state[u] = 2

        for k in kids:
            if k.id not in state:
                dfs(k.id)
        dag = list(dict.fromkeys(dag))

        # 2. longest-path ranking, honour rank= pins
        rank = {k.id: int(k.attrs["rank"]) for k in kids if "rank" in k.attrs}
        preds = defaultdict(list)
        for a, b, _ in dag:
            preds[b].append(a)
        def get_rank(u, seen=()):
            if u in rank:
                return rank[u]
            r = 0
            for p in preds[u]:
                if p not in seen:
                    r = max(r, get_rank(p, seen + (u,)) + 1)
            rank[u] = r
            return r
        for k in kids:
            get_rank(k.id)
        # pull sources down next to their successors (avoids long first edges)
        succ_dag = defaultdict(list)
        for a, b, _ in dag:
            succ_dag[a].append(b)
        for k in kids:
            if not preds[k.id] and succ_dag[k.id] and "rank" not in k.attrs:
                rank[k.id] = min(rank[s] for s in succ_dag[k.id]) - 1

        # 3. virtual nodes for long edges so they bend around ranks
        layers: dict[int, list[str]] = defaultdict(list)
        for k in kids:
            layers[rank[k.id]].append(k.id)
        size = {k.id: (k.w, k.h) for k in kids}
        adj = []  # (upper, lower, weight)
        vcount = 0
        self.virtual_chains = {}
        for a, b, w in dag:
            ra, rb = rank[a], rank[b]
            if rb - ra <= 1:
                adj.append((a, b, w))
                continue
            prev = a
            chain = []
            for r in range(ra + 1, rb):
                vid = f"__v{vcount}"
                vcount += 1
                layers[r].append(vid)
                size[vid] = (0.0, 0.0)
                rank[vid] = r
                adj.append((prev, vid, w))
                chain.append(vid)
                prev = vid
            adj.append((prev, b, w))
            self.virtual_chains[(a, b)] = chain
        lo, hi = min(layers), max(layers)
        order = [layers.get(r, []) for r in range(lo, hi + 1)]
        up, down = defaultdict(list), defaultdict(list)
        for a, b, w in adj:
            down[a].append((b, w))
            up[b].append((a, w))

        # 4. crossing reduction (barycenter sweeps) unless order=source
        if order_mode != "source":
            def pos_of(layer):
                return {u: i for i, u in enumerate(layer)}
            def crossings(ordr):
                c = 0
                for i in range(len(ordr) - 1):
                    p2 = pos_of(ordr[i + 1])
                    es = [(j, p2[v]) for j, u in enumerate(ordr[i]) for v, _ in down[u] if v in p2]
                    c += sum(1 for x in range(len(es)) for y in range(x + 1, len(es))
                             if (es[x][0] - es[y][0]) * (es[x][1] - es[y][1]) < 0)
                return c
            best, best_c = [list(l) for l in order], crossings(order)
            for it in range(8):
                rng = range(1, len(order)) if it % 2 == 0 else range(len(order) - 2, -1, -1)
                nb = up if it % 2 == 0 else down
                for i in rng:
                    ref = pos_of(order[i - 1] if it % 2 == 0 else order[i + 1])
                    def bary(u, i=i, ref=ref):
                        ns = [ref[v] for v, _ in nb[u] if v in ref]
                        return sum(ns) / len(ns) if ns else order[i].index(u)
                    order[i] = sorted(order[i], key=lambda u: (bary(u), idx.get(u, 1e9)))
                c = crossings(order)
                if c < best_c:
                    best, best_c = [list(l) for l in order], c
            order = best

        # 5. cross-axis coordinates
        def csz(u):
            w, h = size[u]
            return h if horizontal else w
        def msz(u):
            w, h = size[u]
            return w if horizontal else h
        vgap = node_gap / 2
        pos: dict[str, float] = {}
        widths = []
        for layer in order:
            x = 0.0
            for u in layer:
                pos[u] = x + csz(u) / 2
                x += csz(u) + (vgap if u.startswith("__v") else node_gap)
            widths.append(x - node_gap if layer else 0)
        maxw = max(widths) if widths else 0
        if balance in ("center", "median"):
            for layer, w in zip(order, widths):
                shift = (maxw - w) / 2
                for u in layer:
                    pos[u] += shift
        elif balance == "end":
            for layer, w in zip(order, widths):
                for u in layer:
                    pos[u] += maxw - w
        if balance == "median":
            pos = self._median_pull(order, pos, up, down, csz, node_gap, vgap)

        # 6. main-axis coordinates
        rank_thick = [max((msz(u) for u in layer), default=0) for layer in order]
        main = 0.0
        main_pos = []
        for t in rank_thick:
            main_pos.append(main)
            main += t + rank_gap
        total_main = main - rank_gap
        minc = min((pos[u] - csz(u) / 2 for layer in order for u in layer), default=0)
        self.virtual_pos = {}
        for ri, layer in enumerate(order):
            for u in layer:
                c = pos[u] - minc
                m = main_pos[ri] + rank_thick[ri] / 2
                if d in ("BT", "RL"):
                    m = total_main - m
                if u.startswith("__v"):
                    self.virtual_pos[u] = (m, c) if horizontal else (c, m)
                    continue
                k = kids[idx[u]]
                if horizontal:
                    k.x, k.y = m - k.w / 2, c - k.h / 2
                else:
                    k.x, k.y = c - k.w / 2, m - k.h / 2
        cross_total = max((pos[u] - minc + csz(u) / 2 for layer in order for u in layer), default=0)
        self._store_waypoints(horizontal)
        return (total_main, cross_total) if horizontal else (cross_total, total_main)

    def _median_pull(self, order, pos, up, down, csz, node_gap, vgap):
        def gap(a, b):
            return (vgap if a.startswith("__v") or b.startswith("__v") else node_gap)
        for it in range(12):
            for li in (range(len(order)) if it % 2 == 0 else range(len(order) - 1, -1, -1)):
                layer = order[li]
                want = {}
                for u in layer:
                    ns = [(pos[v], w) for v, w in up[u] + down[u]]
                    if ns:
                        ns.sort()
                        tot = sum(w for _, w in ns)
                        acc, med = 0.0, ns[0][0]
                        for p, w in ns:
                            acc += w
                            if acc >= tot / 2:
                                med = p
                                break
                        if len(ns) % 2 == 0 and all(w == ns[0][1] for _, w in ns):
                            med = (ns[len(ns) // 2 - 1][0] + ns[len(ns) // 2][0]) / 2
                        want[u] = med
                    else:
                        want[u] = pos[u]
                # place in order keeping min separation, then fix overlaps right-to-left
                new = [want[u] for u in layer]
                for i in range(1, len(layer)):
                    mn = new[i - 1] + (csz(layer[i - 1]) + csz(layer[i])) / 2 + gap(layer[i - 1], layer[i])
                    new[i] = max(new[i], mn)
                # shift block left toward desired mean to avoid drifting right
                if layer:
                    excess = sum(n - want[u] for n, u in zip(new, layer)) / len(layer)
                    new = [n - max(0.0, excess) for n in new]
                    for i in range(1, len(layer)):
                        mn = new[i - 1] + (csz(layer[i - 1]) + csz(layer[i])) / 2 + gap(layer[i - 1], layer[i])
                        new[i] = max(new[i], mn)
                for u, n in zip(layer, new):
                    pos[u] = n
        return pos

    def _store_waypoints(self, horizontal):
        self.g.attrs.setdefault("__dir__", "LR" if horizontal else "TB")
        self.waypoints = {}
        for (a, b), chain in self.virtual_chains.items():
            self.waypoints[(a, b)] = [self.virtual_pos[v] for v in chain]


LAYOUTS = {"layered": LayeredLayout, "grid": GridLayout, "row": LineLayout,
           "column": LineLayout, "radial": RadialLayout, "fixed": FixedLayout}


def layout_group(g: Group, doc: Document) -> None:
    for c in g.children:
        if isinstance(c, Group):
            layout_group(c, doc)
        else:
            size_node(c, doc)
    if "layout" not in g.attrs:
        g.attrs["layout"] = "layered" if local_edges(g, doc) or g.kind == "graph" else "row"
    pt, pr, pb, pl = box4(g.style.get("padding"), 14)
    if not g.children:
        cw, ch = 40.0, 20.0
        lay = None
    else:
        lay = LAYOUTS[g.attrs["layout"]](g, doc)
        cw, ch = lay.run()
    g.label_h = 0.0
    lw = 0.0
    if g.label and g.kind == "group":
        fs = px(g.style.get("font-size"), 12)
        lw, g.label_h, _ = measure(g.label, g.style.get("font-family", "sans-serif"), fs,
                                   g.style.get("font-weight", "normal") in ("bold", "700"))
        g.label_h += 6
    inner_w = max(cw, lw)
    top = g.style.get("label-position", "top") != "bottom"
    g.ox = pl + (inner_w - cw) / 2
    g.oy = pt + (g.label_h if top else 0)
    g.w = inner_w + pl + pr
    g.h = ch + pt + pb + g.label_h
    g.layout_obj = lay


def absolutize(g: Group, ox: float, oy: float) -> None:
    g.ax, g.ay = ox, oy
    for c in g.children:
        c.ax, c.ay = ox + g.ox + c.x, oy + g.oy + c.y
        if isinstance(c, Group):
            absolutize(c, c.ax, c.ay)


def layout(doc: Document) -> None:
    root = doc.root
    layout_group(root, doc)
    absolutize(root, 0, 0)
    # translate virtual waypoints into absolute coords and attach to edges
    for g in [root] + [i for i in doc.walk() if isinstance(i, Group)]:
        lay = getattr(g, "layout_obj", None)
        wps = getattr(lay, "waypoints", None)
        if not wps:
            continue
        for e in doc.edges:
            a = direct_child(doc.items[e.src], g)
            b = direct_child(doc.items[e.dst], g)
            if a is None or b is None:
                continue
            for key, rev in (((a.id, b.id), False), ((b.id, a.id), True)):
                if key in wps and not e.waypoints:
                    pts = [(g.ax + g.ox + x, g.ay + g.oy + y) for x, y in wps[key]]
                    e.waypoints = pts[::-1] if rev else pts
                    e.wp_owner = g
