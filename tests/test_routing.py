# SPDX-FileCopyrightText: 2026 Reza Jelveh
#
# SPDX-License-Identifier: Apache-2.0

"""Routing regressions: edges between the same nodes, and edges fanning out of a
round node, must stay apart and must not cross."""

from predictygraph import _style, parse
from predictygraph.layout import layout
from predictygraph.route import Router

STATES = """graph dir=LR
default node shape=circle
idle "Idle"
running "Running"
error "Error"
done "Done"
idle -> running "Start"
running -> error "Fail"
running -> done "OK"
error -> running "Retry"
done -> idle "Reset"
"""


def _ends():
    doc = _style(parse(STATES), None, None, None)
    layout(doc)
    r = Router(doc).route()
    ends = {}
    for e in doc.edges:
        pts, _ = r.geometry(e)
        ends[(e.src, e.dst)] = (pts[0], pts[-1])
    return ends


def test_edge_and_its_reverse_do_not_overlap():
    ends = _ends()
    fail = ends[("running", "error")]
    retry = ends[("error", "running")]
    # Fail leaves Running at p0, Retry arrives at Running at p1 (and vice versa at Error)
    assert abs(fail[0][1] - retry[1][1]) >= 8, "Fail and Retry share a port on Running"
    assert abs(fail[1][1] - retry[0][1]) >= 8, "Fail and Retry share a port on Error"


def test_edges_leaving_one_side_keep_their_order():
    ends = _ends()
    # on Running's right side: Fail (to Error, top) above Retry above OK (to Done, bottom)
    ys = [ends[("running", "error")][0][1], ends[("error", "running")][1][1], ends[("running", "done")][0][1]]
    assert ys == sorted(ys), f"edges cross on Running's right side: {ys}"


def test_shifted_ports_sit_on_the_circle():
    doc = _style(parse(STATES), None, None, None)
    layout(doc)
    r = Router(doc).route()
    for e in doc.edges:
        pts, _ = r.geometry(e)
        for n, p in ((doc.items[e.src], pts[0]), (doc.items[e.dst], pts[-1])):
            d = ((p[0] - n.cx) / (n.w / 2)) ** 2 + ((p[1] - n.cy) / (n.h / 2)) ** 2
            assert abs(d - 1) < 0.02, f"{e.src}->{e.dst} end is off the outline of {n.id}"


FAN = """graph dir=LR
group site layout=column gap=12 {
  g "GPU servers" shape=box
}
api "Sovereign API" shape=box
group sys layout=column gap=12 {
  idp "Login" shape=box
  bill "Billing and ERP integration" shape=box
  ui "Portal for everyone" shape=box
}
api -> idp
api -> bill
api -> ui
g -> api
"""


def _curve_points(segs, n=40):
    pts, cur = [], None
    for s in segs:
        if s[0] == "M":
            cur = s[1:3]
            pts.append(cur)
        elif s[0] == "C":
            (x0, y0), (x1, y1, x2, y2, x3, y3) = cur, s[1:]
            for i in range(1, n + 1):
                t = i / n
                u = 1 - t
                pts.append((u**3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t**3 * x3, u**3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t**3 * y3))
            cur = (x3, y3)
    return pts


def _crosses(a, b):
    def ccw(p, q, r):
        return (r[1] - p[1]) * (q[0] - p[0]) - (q[1] - p[1]) * (r[0] - p[0])

    for p, q in zip(a, a[1:]):
        for r, s in zip(b, b[1:]):
            if ccw(p, r, s) * ccw(q, r, s) < 0 and ccw(p, q, r) * ccw(p, q, s) < 0:
                return True
    return False


def test_curved_fan_out_to_targets_at_different_distances_does_not_cross():
    """Targets of different widths put their ports at different x; each S-curve used to
    swing at its own midpoint, so the fan crossed although the source ports were ordered."""
    doc = _style(parse(FAN), None, None, None)
    layout(doc)
    r = Router(doc).route()
    paths = []
    for e in doc.edges:
        if e.src == "api":
            pts, axis = r.geometry(e)
            paths.append(_curve_points(r.path_segs(pts, axis, "curve", 6, None, r.curve_level.get(e.id), None)))
    assert len(paths) == 3
    for i in range(3):
        for j in range(i + 1, 3):
            assert not _crosses(paths[i], paths[j])
