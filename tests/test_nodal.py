from nodal import render
from nodal.parser import NodalSyntaxError, parse

import pytest


def test_edge_chain_and_fanout():
    doc = parse("a, b -> c ==> d\n")
    pairs = [(e.src, e.dst, e.body) for e in doc.edges]
    assert pairs == [("a", "c", "solid"), ("b", "c", "solid"), ("c", "d", "thick")]


@pytest.mark.parametrize("tok,arrow", [("->", "end"), ("<-", "start"), ("<->", "both"),
                                        ("--", "none"), ("<..>", "both"), ("==>", "end")])
def test_arrow_tokens(tok, arrow):
    assert parse(f"a {tok} b").edges[0].arrow == arrow


def test_groups_and_scoping():
    doc = parse('group g "G" layout=grid cols=2 {\n x; y\n}\nx -> y\n')
    assert doc.items["x"].parent.id == "g"
    assert doc.items["g"].attrs["layout"] == "grid"


def test_errors_have_line_numbers():
    with pytest.raises(NodalSyntaxError, match="line 2"):
        parse("a\ngroup g {\n")


def test_render_mixed_layouts_and_css():
    svg = render('graph dir=LR edge-width=3\ncss { node.x { fill: #ff0000; } }\n'
                 'group a layout=layered dir=TB { p -> q }\n'
                 'group b layout=radial { h; i; j }\n'
                 'n .x\np -> h "lbl" width=5 head=diamond\n')
    assert 'fill="#ff0000"' in svg
    assert 'stroke-width="5"' in svg and 'stroke-width="3"' in svg
    assert "lbl" in svg


def test_spine_is_centred_over_odd_fanout():
    import re
    svg = render('graph dir=TB\nA "Christmas"\nB "Go shopping"\nC "Let me think" shape=diamond\n'
                 'D "Laptop"\nE "iPhone"\nF "Car"\nA -> B -> C\nC -> D\nC -> E\nC -> F\n')

    def cx(nid):
        body = svg.split(f'<g id="{nid}"', 1)[1].split("</g>", 1)[0]
        m = re.search(r'<rect x="([\d.]+)" y="[\d.]+" width="([\d.]+)"', body)
        if m:
            return float(m[1]) + float(m[2]) / 2
        xs = [float(p.split(",")[0]) for p in re.search(r'points="([^"]+)"', body)[1].split()]
        return (min(xs) + max(xs)) / 2

    centres = [cx(n) for n in "ABCE"]
    assert max(centres) - min(centres) < 1.0


def test_animation_svg_and_frames():
    src = 'graph dir=LR\na border=march\nb border=pulse\nc border=glow\na -> b flow=forward\nb <-> c flow=auto\n'
    svg = render(src)
    assert svg.count("<animate ") >= 5
    assert "nodal-flow-forward" in svg and "nodal-flow-reverse" in svg
    f0, f1 = render(src, t=0.0), render(src, t=0.4)
    assert "<animate" not in f0 and f0 != f1
    plain = render("a -> b\n")
    assert "<animate" not in plain and "nodal-flow" not in plain


def test_loop_length():
    from nodal.anim import loop_length
    assert loop_length([1.2, 0.8]) == 2.4
    assert loop_length([]) == 1.0
    assert loop_length([7, 11]) == 11  # LCM 77s > cap -> longest track
