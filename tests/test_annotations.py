# SPDX-FileCopyrightText: 2026 The predictygraph Authors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Subtitles, step badges, legend, caption, accent bars and header bands."""
from predictygraph import build_scene
from predictygraph.parser import parse


def scene(src):
    doc = parse(src)
    return doc, build_scene(doc)


def classes(sc):
    out, stack = [], list(sc.layers)
    while stack:
        e = stack.pop()
        out.append(e.cls or "")
        stack += e.children
    return " ".join(out)


def texts(sc):
    out, stack = [], list(sc.layers)
    while stack:
        e = stack.pop()
        if e.kind == "text":
            out.append(e.geom["text"])
        stack += e.children
    return out


def test_sub_adds_height_and_is_drawn():
    plain, _ = scene('a "Title"\n')
    doc, sc = scene('a "Title" sub="second line"\n')
    assert doc.items["a"].h > plain.items["a"].h
    assert "second line" in texts(sc)


def test_sub_is_not_bold_and_smaller():
    doc, _ = scene('css { node { font-weight: bold; font-size: 20px; } }\na "T" sub="s"\n')
    st = doc.items["a"].sub_style
    assert "font-weight" not in st or st["font-weight"] == "normal"
    assert float(st["font-size"].rstrip("px")) < 20


def test_group_sub_drawn_under_title():
    doc, sc = scene('group g "Panel" sub="what it does" {\n a\n}\n')
    assert "what it does" in texts(sc)
    assert doc.items["g"].label_h > doc.items["g"].title_h


def test_steps_auto_and_explicit():
    doc, sc = scene("graph steps=auto\na -> b\nb -> c step=9\nc -> d\n")
    assert [e.attrs["step"] for e in doc.edges] == ["1", "9", "2"]
    assert classes(sc).count("pdg-step") == 3


def test_legend_and_caption_grow_canvas():
    _, base = scene("a -> b\n")
    _, sc = scene('graph caption="Figure 1"\na -> b\nlegend "Key"\nlegend .green "HAMi"\n')
    assert sc.height > base.height
    assert {"Key", "HAMi", "Figure 1"} <= set(texts(sc))
    assert "pdg-legend-box" in classes(sc)


def test_accent_bar_widens_node_and_draws():
    plain, _ = scene('a "a longer label"\n')
    doc, sc = scene('css { node { accent-bar: 5px #0f0; } }\na "a longer label"\n')
    assert doc.items["a"].w == plain.items["a"].w + 5
    assert "pdg-accent" in classes(sc)


def test_title_fill_band():
    _, sc = scene('css { group { title-fill: #dbeafe; } }\ngroup g "G" {\n a\n}\n')
    assert "pdg-title-band" in classes(sc)


def test_bracket_widens_canvas_and_draws_note():
    _, base = scene('graph layout=column\na\nb\nc\n')
    _, sc = scene('graph layout=column\na\nb\nc\nbracket a, b "first two"\nbracket a, c "all"\n')
    assert sc.width > base.width
    assert {"first two", "all"} <= set(texts(sc))
    assert classes(sc).count("pdg-bracket-line") == 2


def test_bracket_unknown_id_is_an_error():
    import pytest
    from predictygraph.parser import PdgSyntaxError
    with pytest.raises(PdgSyntaxError):
        parse('a\nbracket a, nope "x"\n')


def test_left_label_is_rotated_and_takes_a_column():
    src = 'css { group { label-position: left; } }\ngroup g "Kernel space" {\n a\n}\n'
    doc, sc = scene(src)
    g = doc.items["g"]
    assert g.side_w > 0
    rotated = []
    stack = list(sc.layers)
    while stack:
        e = stack.pop()
        if e.kind == "text" and e.geom.get("rotate"):
            rotated.append(e.geom["text"])
        stack += e.children
    assert rotated == ["Kernel space"]
