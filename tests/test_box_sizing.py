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
