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
