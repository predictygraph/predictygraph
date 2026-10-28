"""Regression tests for labels, ER heads, empty-label circles and the label selector."""
from nodal import build_scene, parse, render


def _node_rect(sc, nid):
    el = next(e for e in sc.walk() if e.id == nid)
    return next(c for c in el.children if c.kind in ("rect", "ellipse")).geom


def test_empty_label_circle_is_round():
    g = _node_rect(build_scene(parse('s "" shape=circle\ns -> a\n')), "s")
    assert g["rx"] == g["ry"] and g["rx"] * 2 <= 20


def test_fanout_labels_do_not_overlap():
    sc = build_scene(parse('graph route=ortho\nC\nC -> D "One"\nC -> E "Two"\nC -> F "Three"\n'))
    boxes = [(g["x"], g["y"], g["w"], g["h"]) for g in (e.geom for e in sc.walk() if e.cls == "nodal-label-bg")]
    assert len(boxes) == 3
    for i, (x, y, w, h) in enumerate(boxes):
        for (x2, y2, w2, h2) in boxes[i + 1:]:
            assert x + w <= x2 or x2 + w2 <= x or y + h <= y2 or y2 + h2 <= y


def test_er_heads_and_head_start():
    svg = render("graph route=ortho\na -- b arrow=both head=many head-start=one\n")
    assert svg.count('class="nodal-head"') == 2


def test_label_selector():
    svg = render('css { edge.hot label { color: #ff0000; font-size: 15px; } }\na -> b "x" .hot\n')
    assert 'fill="#ff0000"' in svg and 'font-size="15"' in svg
