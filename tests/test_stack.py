# SPDX-FileCopyrightText: 2026 The predictygraph Authors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""align=stretch tiers, same-side C-shaped edges, theme css."""
from predictygraph import build_scene
from predictygraph.parser import parse
from predictygraph.theme import theme_css


def test_stretch_makes_tiers_equal_width():
    doc = parse("graph layout=column align=stretch\ngroup a {\n x\n}\ngroup b {\n p\n q\n r\n}\n")
    build_scene(doc)
    assert doc.items["a"].w == doc.items["b"].w


def test_same_side_edge_goes_around_boxes_between():
    src = ("graph layout=column\nlong \"a fairly wide box\"\nmid \"an even wider box in the middle\"\n"
           "low \"low\"\nlong -> low exit=left enter=left route=ortho\n")
    doc = parse(src)
    build_scene(doc)
    from predictygraph.route import Router
    pts, _ = Router(doc).geometry(doc.edges[0])
    assert min(x for x, _ in pts) < doc.items["mid"].ax


def test_hami_theme_has_extra_css():
    css = theme_css("hami")
    assert "accent-bar" in css and "title-fill" in css
