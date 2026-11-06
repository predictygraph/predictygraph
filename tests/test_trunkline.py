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


def test_fan_spread_straightens_the_near_level_branch():
    src = 'graph dir=LR route=ortho diagonal=always balance=center\ngroup f layout=column gap=60 { a "A"\n b "B" }\ngroup s layout=column { s1 "1"\n s2 "2"\n s3 "3"\n s4 "4"\n s5 "5"\n s6 "6" }\na -> s1, s2, s3 fan=spread\nb -> s4, s5, s6 fan=spread\n'
    from predictygraph import _layout_and_route, _style, parse

    doc = parse(src)
    _style(doc, None, None, None)
    router = _layout_and_route(doc)
    flat = 0
    for e in doc.edges:
        pts, _ = router.geometry(e)
        flat += abs(pts[0][1] - pts[-1][1]) < 0.5
    assert flat == 2
