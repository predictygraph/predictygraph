# SPDX-FileCopyrightText: 2026 Reza Jelveh
#
# SPDX-License-Identifier: Apache-2.0

import re
from predictygraph import render


def test_draw_ring_grid():
    svg = render("graph theme=trunkline grid=40\na -> b flow=draw\nb -> c flow=forward\n")
    assert "pdg-grid" in svg and "pdg-draw" in svg and "pdg-flow-ring" in svg


def test_static_draw_is_complete():
    svg = render("graph\na -> b flow=draw\n", t=0)
    assert 'stroke-dashoffset="0"' in svg


def test_label_above_sits_outside_the_outline():
    svg = render('graph\ngroup g "Rail" { a "A" }\ncss { group { label-position: above; stroke: #000; } }')
    ty = float(re.search(r'<text[^>]*y="([\d.]+)"[^>]*>Rail', svg).group(1))
    oy = min(float(y) for y in re.findall(r'<rect[^>]*y="([\d.]+)"', svg))
    assert ty < oy + 1


def test_fan_spread_turns_together_at_45():
    from predictygraph.route import Diagonal, octilinear
    d = Diagonal("auto", 1e9, 45.0, True)
    a = octilinear((0, 0), (200, 40), "h", None, 30, d)
    b = octilinear((0, 10), (200, 120), "h", None, 30, d)
    assert a[1][0] == b[1][0] == 30  # both turn right after the stub
    for p in (a, b):
        assert abs(abs(p[2][0] - p[1][0]) - abs(p[2][1] - p[1][1])) < 0.01  # 45°
