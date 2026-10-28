"""Scene IR + routing behaviour: lanes, rank clearance, title clearance, writers."""
import re

from nodal import build_scene, parse, render, write_svg
from nodal.ir import Scene


def _scene(src):
    return build_scene(parse(src))


def _edge_path(svg, eid):
    body = svg.split(f'<g id="{eid}"', 1)[1].split("</g>", 1)[0]
    return re.search(r' d="([^"]+)"', body)[1]


def _runs(d):
    """Horizontal runs (y, x0, x1) of a path d string."""
    pts = [(float(x), float(y)) for x, y in re.findall(r"(-?[\d.]+) (-?[\d.]+)", d)]
    return [(p[1], min(p[0], q[0]), max(p[0], q[0])) for p, q in zip(pts, pts[1:])
            if abs(p[1] - q[1]) < 0.01 and abs(p[0] - q[0]) > 1]


LANES = '''graph dir=TB route=bend diagonal=none
group top layout=row gap=60 { a; b; m; c }
t
a -> t
b ..> t
c -> t
m -> t constraint=false
'''


def test_distinct_traces_get_separate_lanes():
    svg = render(LANES)
    ya = _runs(_edge_path(svg, "e0"))[0][0]
    yb = _runs(_edge_path(svg, "e1"))[0][0]
    assert abs(ya - yb) >= 6


def test_same_style_fan_in_merges_into_bus():
    svg = render(LANES.replace("b ..> t", "b -> t"))
    assert _runs(_edge_path(svg, "e0"))[0][0] == _runs(_edge_path(svg, "e1"))[0][0]


def test_runs_keep_clear_of_boxes_and_gap_widens():
    tight = LANES.replace("graph dir=TB", "graph dir=TB rank-gap=14")
    sc = _scene(tight)
    svg = write_svg(sc)
    # every horizontal run stays >= 10px from both outer boxes (top group, node t)
    boxes = {}
    for el in sc.walk():
        if el.id in ("top", "t"):
            r = next(c for c in el.children if c.kind == "rect").geom
            boxes[el.id] = (r["y"], r["y"] + r["h"])
    for eid in ("e0", "e1", "e2"):
        for y, _, _ in _runs(_edge_path(svg, eid)):
            assert y - boxes["top"][1] >= 10 and boxes["t"][0] - y >= 10


def test_group_title_is_not_crossed():
    from nodal.text import measure
    src = '''graph dir=TB route=bend
a
group g "A LONG GROUP TITLE" layout=row { b; c }
a -> b
'''
    sc = _scene(src)
    svg = write_svg(sc)
    title = next(e for e in sc.walk() if e.kind == "text" and e.geom["text"] == "A LONG GROUP TITLE")
    tw, th, _ = measure(title.geom["text"], title.paint["font-family"], title.paint["font-size"], True)
    x0, x1 = title.geom["x"], title.geom["x"] + tw
    y1 = title.geom["y"]
    y0 = y1 - th
    pts = [(float(x), float(y)) for x, y in re.findall(r"(-?[\d.]+) (-?[\d.]+)", _edge_path(svg, "e0"))]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        if min(ay, by) <= y1 and max(ay, by) >= y0:  # segment spans the title band
            assert max(ax, bx) < x0 - 2 or min(ax, bx) > x1 + 2


def test_scene_is_format_independent_and_frames_differ():
    sc = _scene("graph dir=LR\na border=pulse\na -> b flow=forward\n")
    assert isinstance(sc, Scene) and sc.durations()
    assert "<animate" in write_svg(sc)
    f0, f1 = write_svg(sc, 0.0), write_svg(sc, 0.3)
    assert "<animate" not in f0 and f0 != f1
