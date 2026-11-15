# SPDX-FileCopyrightText: 2026 Reza Jelveh
#
# SPDX-License-Identifier: Apache-2.0

"""`sketch:` hand-drawn strokes, `hatch:` fills, Lucide `icon=`, `$var` classes in defs."""

import re

import pytest

from predictygraph import render
from predictygraph.sketch import hatch


def _node(svg, nid):
    return svg.split(f'<g id="{nid}"', 1)[1].split("</g>", 1)[0]


def test_hatch_lines_stay_inside_the_box():
    el = hatch(10, 20, 100, 50, "#333", gap=10)
    pts = [(s[1], s[2]) for s in el.geom["segs"]]
    assert len(pts) == 2 * 15  # (w + h) / gap lines
    assert all(10 - 1e-6 <= x <= 110 + 1e-6 and 20 - 1e-6 <= y <= 70 + 1e-6 for x, y in pts)
    for m, line in zip(el.geom["segs"][::2], el.geom["segs"][1::2]):  # 45 degrees, rising
        assert abs((line[1] - m[1]) + (line[2] - m[2])) < 1e-6


def test_hatch_draws_between_fill_and_outline():
    svg = render('css { .w { hatch: #123456; } }\na "" .w width=80 height=60')
    body = _node(svg, "a")
    i_fill, i_hatch = body.index('stroke="none"'), body.index('stroke="#123456"')
    assert i_fill < i_hatch < body.index('fill="none"', i_hatch + 1)


def test_sketch_is_deterministic_and_doubles_strokes():
    src = "graph sketch=1\na -> b"
    one, two = render(src), render(src)
    assert one == two
    edge = one.split('<g id="e0"', 1)[1].split("</g>", 1)[0]
    assert len(re.findall(r"<path ", edge)) >= 2
    assert " C " in edge


def test_sketch_off_by_default():
    edge = render("a -> b").split('<g id="e0"', 1)[1].split("</g>", 1)[0]
    assert len(re.findall(r"<path ", edge)) == 1


def test_lucide_icon():
    pytest.importorskip("lucide")
    svg = render('css { .u { fill: #ffe6cc; stroke: #d79b00; } }\nu "User" .u icon=user')
    assert "data:image/svg+xml;base64," in _node(svg, "u")


def test_unknown_lucide_icon_is_an_error():
    pytest.importorskip("lucide")
    with pytest.raises(ValueError, match="unknown Lucide icon"):
        render("u icon=no-such-icon-xyz")


def test_def_class_from_variable():
    svg = render('css { .w { fill: #abcdef; } }\ndef g c=x {\n  t "" .$c\n}\nuse g k c=w')
    assert 'class="pdg-node w"' in svg


def test_edge_image(tmp_path):
    from PIL import Image

    Image.new("RGBA", (10, 10), "green").save(tmp_path / "logo.png")
    (tmp_path / "d.pdg").write_text("a -> b image=logo.png img-width=20")
    svg = render((tmp_path / "d.pdg").read_text(), base_dir=str(tmp_path))
    edge = svg.split('<g id="e0"', 1)[1].split("</g>", 1)[0]
    assert 'class="pdg-edge-image"' in edge and 'width="20"' in edge


def test_sketch_keeps_corners():
    svg = render("graph route=ortho\na\nb at=0,0\na -> b exit=right enter=top sketch=1 roughness=0.01")
    edge = svg.split('<g id="e0"', 1)[1].split("</g>", 1)[0]
    assert edge.count(" C ") >= 4  # two passes x at least two runs


def test_label_at_start_has_no_background():
    svg = render('graph route=ortho\na\nb\na -> b "x" exit=right enter=top label-at=start')
    edge = svg.split('<g id="e0"', 1)[1].split("</g>", 1)[0]
    assert "pdg-label-bg" not in edge and ">x<" in edge


def test_diagonal_always_slants_every_jog():
    from predictygraph.route import Diagonal, octilinear

    diag = Diagonal("auto", 1e9, 45.0)
    for cross in (18.0, 35.0, 78.0):
        pts = octilinear((0.0, 0.0), (cross, 48.0), "v", None, 9.0, diag)
        assert len(pts) == 4 and pts[1][0] != pts[2][0] and pts[1][1] != pts[2][1]
