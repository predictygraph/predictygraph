# SPDX-FileCopyrightText: 2026 Reza Jelveh
#
# SPDX-License-Identifier: Apache-2.0

"""Theme TOML: palette aliases and [classes] (named colour roles for nodes, groups, edges)."""

import pytest

from predictygraph import build_scene
from predictygraph.parser import parse
from predictygraph.theme import ThemeError, theme_css

BASE = """schema = 1
[palette]
bg = "#ffffff"
surface = "#f0f4f8"
fg = "#151915"
muted = "#808080"
border = "#dde3e8"
red = "#d32f2f"
orange = "#e8a33d"
yellow = "#e8f3cc"
green = "#a8d729"
cyan = "#29c9a3"
blue = "#093034"
purple = "#4a584a"
lime = "green"
ink = "blue"
"""


def _theme(tmp_path, extra="", top=""):
    p = tmp_path / "t.toml"
    p.write_text(top + BASE + extra)
    return p


def test_palette_aliases_and_classes(tmp_path):
    p = _theme(tmp_path, '[classes]\nlime = { fill = "lime", color = "ink", sub = "muted" }\n')
    css = theme_css(str(p))
    assert "--lime: #a8d729;" in css and "--ink: #093034;" in css
    doc = parse(f'graph theme={p}\na "A" .lime sub="s"\nb "B"\na -> b .lime\n')
    build_scene(doc)
    a = doc.items["a"]
    assert a.style["fill"] == "#a8d729" and a.style["stroke"] == "#a8d729" and a.style["color"] == "#093034"
    assert a.sub_style["color"] == "#808080"
    assert doc.edges[0].style["stroke"] == "#a8d729"


def test_classes_set_font_weights(tmp_path):
    p = _theme(tmp_path, "[classes]\nregular = { font-weight = 400, sub-weight = 700 }\n")
    doc = parse(f'graph theme={p}\ncss {{ node {{ font-weight: 700; }} sub {{ font-weight: 400; }} }}\na "A" .regular sub="s"\n')
    build_scene(doc)
    a = doc.items["a"]
    assert str(a.style["font-weight"]) == "400" and str(a.sub_style["font-weight"]) == "700"


def test_utilities_pick_palette_colours_and_weights_by_class(tmp_path):
    p = _theme(tmp_path, top="utilities = true\n")
    doc = parse(f'graph theme={p}\na "A" .green .fill-ink .text-lime .regular\nb "B"\na -> b .stroke-muted\n')
    build_scene(doc)
    a = doc.items["a"]
    assert a.style["fill"] == "#093034" and a.style["color"] == "#a8d729" and str(a.style["font-weight"]) == "400"
    assert a.style["stroke"] == "#a8d729"  # .green's stroke stays
    assert doc.edges[0].style["stroke"] == "#808080"


def test_unknown_class_key_is_an_error(tmp_path):
    with pytest.raises(ThemeError):
        theme_css(str(_theme(tmp_path, '[classes]\nx = { colour = "ink" }\n')))


def test_generic_classes_work_in_every_theme(tmp_path):
    p = _theme(tmp_path)
    doc = parse(f'graph theme={p}\na "A" .label\nb "B" .card\nc "C" .on-blue sub="s"\nd "D" .on-yellow\ne "E" .quiet\n')
    build_scene(doc)
    it = doc.items
    assert it["a"].style["fill"] == "none" and str(it["a"].style["font-weight"]) == "400"
    assert it["b"].style["fill"] == "#ffffff" and it["b"].style["stroke"] == "#dde3e8"
    # .on-<name>: the fill plus whichever of fg/bg reads better on it, subtitle included
    assert it["c"].style["fill"] == "#093034" and it["c"].style["color"] == "#ffffff"
    assert it["c"].sub_style["color"] == "#ffffff"
    assert it["d"].style["color"] == "#151915"
    assert it["e"].style["color"] == "#808080"


def test_palette_on_entry_sets_the_text_colour_of_on_classes(tmp_path):
    p = _theme(tmp_path, 'on-cyan = "bg"\n')
    doc = parse(f'graph theme={p}\na "A" .on-cyan\n')
    build_scene(doc)
    assert doc.items["a"].style["color"] == "#ffffff"
    assert "on-on-cyan" not in theme_css(str(p))
