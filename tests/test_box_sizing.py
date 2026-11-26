# SPDX-FileCopyrightText: 2026 Reza Jelveh
#
# SPDX-License-Identifier: Apache-2.0

"""Box sizing: graph padding, group width=, CSS width, .bare, justify=fill, fan buses."""

import re
from typing import Any

from predictygraph import render
from predictygraph.layout import layout
from predictygraph.parser import parse
from predictygraph.style import apply_styles
from predictygraph.styleutil import text_block


def _doc(src):
    doc = parse(src)
    apply_styles(doc)
    layout(doc)
    return doc


def _item(doc, iid) -> Any:
    def walk(g):
        for k in g.children:
            if k.id == iid:
                return k
            if hasattr(k, "children") and (hit := walk(k)):
                return hit

    hit = walk(doc.root)
    assert hit is not None, iid
    return hit


def test_attribute_value_ends_at_semicolon():
    doc = _doc('graph layout=row\na "" width=9; b "B"\n')
    assert _item(doc, "b") is not None


def test_graph_padding_zero_is_honoured():
    svg = render('graph layout=row padding=0\na "A"\n', t=0)
    assert re.search(r'<rect x="0" y="0"', svg)


def test_group_width_sets_a_minimum_size():
    doc = _doc('graph layout=row\ngroup g "G" width=200 { x "x" }\n')
    assert _item(doc, "g").w == 200


def test_css_width_and_height_size_a_node():
    doc = _doc('graph\ncss { node.s { width: 60px; height: 30px; } }\na "" .s\n')
    a = _item(doc, "a")
    assert (a.w, a.h) == (60, 30)


def test_bare_group_has_no_box_and_no_padding():
    doc = _doc('graph\ngroup g .bare { a "A" }\n')
    g, a = _item(doc, "g"), _item(doc, "a")
    assert g.style["fill"] == "none" and (g.w, g.h) == (a.w, a.h)


def test_justify_fill_shares_the_stretched_width():
    doc = _doc(
        "graph layout=column align=stretch\n"
        'top "a long label that sets the width of the column"\n'
        "group r layout=row gap=10 justify=fill .bare {\n"
        '  group a "A" { x "x" }\n'
        '  group b "B" { y "y" }\n'
        "}\n"
    )
    r, a, b = _item(doc, "r"), _item(doc, "a"), _item(doc, "b")
    assert abs(a.w - b.w) < 0.5
    assert abs(a.w + b.w + 10 - r.w) < 0.5


def test_mixed_fan_merges_into_one_bus():
    svg = render(
        "graph layout=row gap=36 align=center\n"
        'b "B" width=140 height=80\n'
        "group labs layout=column gap=4 .bare {\n"
        '  l1 "one" height=14\n  l2 "two" height=14\n  l3 "three" height=14\n  l4 "four" height=14\n'
        "}\n"
        "b -> l1, l2, l3, l4 route=ortho\n",
        t=0,
    )
    starts = {m for m in re.findall(r' d="M ([\d.]+ [\d.]+)', svg)}
    assert len(starts) == 1  # all four leave B from one point


def test_lr_rank_gap_fits_a_long_edge_label():
    doc = _doc('graph dir=LR rank-gap=20\na "A"\nb "B"\na -> b "a fairly long edge label"\n')
    a, b = _item(doc, "a"), _item(doc, "b")
    lw = text_block("a fairly long edge label", {}, 11, bold=False)[0]
    assert b.ax - (a.ax + a.w) >= lw  # the label runs along the gap, so all of it fits


NARROW = (
    "graph layout=column gap=40 align=start\n"
    'top "a very wide box that spans the narrow one below it" width=600\n'
    'n "narrow" width=80\n'
    "top -> n route=ortho\n"
)


def test_straight_edge_runs_through_the_narrower_box_centre():
    x = float(re.search(r' d="M ([\d.]+)', render(NARROW, t=0))[1])
    assert abs(x - _item(_doc(NARROW), "n").cx) < 0.5


EM = """graph
css {
  graph { font-size: 20px; }
  group { font-size: 0.5em; }
  node.big { font-size: 1.5em; }
  edge { font-size: 75%; }
}
group g "G" { a "plain"; b "big" .big }
a -> b "label"
"""


def test_nodes_take_the_graph_font_size_and_em_is_relative_to_it():
    doc = _doc(EM)
    g, a, b = _item(doc, "g"), _item(doc, "a"), _item(doc, "b")
    assert a.style["font-size"] == "20.0px"  # the graph's size, not the group title's 10px
    assert b.style["font-size"] == "30.00px"
    assert g.style["font-size"] == "10.00px"
    assert doc.edges[0].style["font-size"] == "15.00px"


def test_a_wider_graph_stretches_a_stretched_column():
    """graph min-width (decktile: the column width) reaches tiers like CSS stretch does."""
    doc = _doc(
        'graph layout=column align=stretch\ncss { graph { min-width: 500px; } }\ngroup r layout=row gap=10 justify=fill .bare { a "A"; b "B" }\n'
    )
    r, a, b = _item(doc, "r"), _item(doc, "a"), _item(doc, "b")
    assert abs(r.w - (500 - 32)) < 0.5 and abs(a.w - b.w) < 0.5 and abs(a.w + b.w + 10 - r.w) < 0.5


def test_rem_is_the_graph_size_even_for_subtitles_and_labels():
    doc = _doc(
        "graph layout=row\ncss { graph { font-size: 20px; } node { font-size: 30px; } sub { font-size: 0.5rem; } label { font-size: 0.6rem; } }\n"
        'a "A" sub="s"\nb "B"\na -> b "l"\n'
    )
    assert _item(doc, "a").sub_style["font-size"] == "10.00px"  # 0.5 x graph, not x node
    assert doc.edges[0].label_style["font-size"] == "12.00px"
