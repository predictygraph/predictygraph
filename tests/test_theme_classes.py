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


def _theme(tmp_path, extra=""):
    p = tmp_path / "t.toml"
    p.write_text(BASE + extra)
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


def test_unknown_class_key_is_an_error(tmp_path):
    with pytest.raises(ThemeError):
        theme_css(str(_theme(tmp_path, '[classes]\nx = { colour = "ink" }\n')))
