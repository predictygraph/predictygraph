# SPDX-FileCopyrightText: 2026 Reza Jelveh
#
# SPDX-License-Identifier: Apache-2.0

"""Edge via= bend points and node layer=back."""

import re

import pytest

from predictygraph import render


def _path(svg, eid):
    body = svg.split(f'<g id="{eid}"', 1)[1].split("</g>", 1)[0]
    return re.search(r' d="([^"]+)"', body)[1]


def _pts(d):
    out = []
    for x, y in re.findall(r"(-?[\d.]+) (-?[\d.]+)", d):
        p = (float(x), float(y))
        if not out or out[-1] != p:  # corners repeat their point
            out.append(p)
    return out


FIXED = """graph layout=fixed padding=0
a "A" at=0,0 width=40 height=20
b "B" at=200,100 width=40 height=20
a -- b via="20,60 220,60"
"""


def test_via_draws_through_the_points_and_leaves_straight_out():
    pts = _pts(_path(render(FIXED), "e0"))
    xs = {round(x) for x, _ in pts}
    ys = {round(y) for _, y in pts}
    # vertical out of A's bottom, along y=60, vertical into B's top
    assert len(pts) == 4
    assert pts[0][0] == pytest.approx(pts[1][0]) and pts[2][0] == pytest.approx(pts[3][0])
    assert pts[1][1] == pytest.approx(pts[2][1])
    assert len(xs) == 2 and len(ys) == 3


def test_via_points_follow_the_root_frame_in_any_layout():
    svg = render('graph dir=TB padding=0\na "A"\nb "B"\na -> b via="200,40"')
    pts = _pts(_path(svg, "e0"))
    assert any(abs(x - pts[0][0]) > 50 for x, _ in pts)  # the path detours to x=200


def test_via_rejects_bad_points():
    with pytest.raises(ValueError, match="via"):
        render('graph layout=fixed\na "A" at=0,0\nb "B" at=99,0\na -- b via="10;x"')


def test_layer_back_draws_the_node_under_the_edges():
    src = """graph layout=fixed padding=0
bg "" at=0,0 width=200 height=100 layer=back fill=#eeeeee
a "A" at=10,40 width=30 height=20
b "B" at=160,40 width=30 height=20
a -> b
"""
    svg = render(src)
    assert svg.index("pdg-back") < svg.index("pdg-edges") < svg.index('class="pdg-nodes"')


def test_layer_back_from_css():
    src = 'graph layout=fixed\ncss { node.bg { layer: back; } }\nbg "" .bg at=0,0 width=99 height=40\na "A" at=0,60\n'
    assert "pdg-back" in render(src)
