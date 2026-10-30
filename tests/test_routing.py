# SPDX-FileCopyrightText: 2026 The predictygraph Authors
#
# SPDX-License-Identifier: GPL-3.0-or-later

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
