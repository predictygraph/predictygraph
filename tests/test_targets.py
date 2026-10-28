# SPDX-FileCopyrightText: 2026 The predictygraph Authors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Render targets: which fonts measure labels, @target CSS blocks, and font warnings."""
import warnings

import pytest

from predictygraph import FontWarning, build_scene, parse
from predictygraph.fonts import FontResolver, bundled, families
from predictygraph.text import measure, use_target

LONG = "device-plugin + vgpu-monitor :9394"


def node_width(src: str, target: str | None, node: str = "a") -> float:
    doc = parse(src)
    build_scene(doc, target=target)
    return doc.items[node].w


def test_families_parses_css_list():
    assert families('"DejaVu Sans", Arial , sans-serif') == ["dejavu sans", "arial", "sans-serif"]
    assert families("") == ["sans-serif"]
    assert families("-evil") == ["sans-serif"]


def test_all_bundled_fonts_exist():
    for fam in ("dejavu sans", "liberation sans", "liberation serif", "liberation mono", "carlito"):
        for bold in (False, True):
            assert bundled(fam, bold), fam


def test_aliases_measure_like_their_metric_twin():
    assert bundled("arial", False) == bundled("liberation sans", False)
    assert bundled("calibri", True) == bundled("carlito", True)
    assert bundled("helvetica neue", False) == bundled("liberation sans", False)


def test_linux_target_measures_dejavu_regardless_of_host():
    with use_target("linux"):
        w_linux, _, _ = measure(LONG, '"DejaVu Sans", sans-serif', 13)
    # 236.2 with raqm shaping, 235.0 with Pillow's basic layout (e.g. macOS wheels)
    assert w_linux == pytest.approx(236.2, abs=1.5)


def test_windows_target_uses_arial_metrics_for_sans_serif():
    with use_target("windows"):
        w_win, _, _ = measure(LONG, "sans-serif", 13)
    with use_target("linux"):
        w_lin, _, _ = measure(LONG, "sans-serif", 13)
    assert w_win < w_lin  # Arial (Liberation Sans) is narrower than DejaVu Sans


def test_web_target_takes_the_widest_font_in_the_list():
    with use_target("web"):
        w_web, _, _ = measure(LONG, '"Liberation Sans", "DejaVu Sans", sans-serif', 13)
    with use_target("linux"):
        w_dv, _, _ = measure(LONG, '"DejaVu Sans"', 13)
    assert w_web == pytest.approx(w_dv)


def test_target_changes_box_width():
    src = 'graph\na "device-plugin + vgpu-monitor :9394"\n'
    assert node_width(src, "web") > node_width(src, "windows")


def test_graph_target_attribute_and_override():
    src = 'graph target=windows\na "device-plugin + vgpu-monitor :9394"\n'
    assert node_width(src, None) == pytest.approx(node_width(src.replace("windows", "linux"), "windows"))
    assert node_width(src, "linux") > node_width(src, None)


def test_unknown_target_is_an_error():
    with pytest.raises(ValueError, match="unknown target"):
        build_scene(parse("graph target=amiga\na\n"))
    with pytest.raises(ValueError):
        FontResolver("amiga")


def text_width(src: str, target: str | None, node: str = "a") -> float:
    doc = parse(src)
    build_scene(doc, target=target)
    return doc.items[node].text_w


def test_target_css_block_only_applies_to_its_target():
    src = ('graph\ncss {\n  node { font-size: 10px; }\n  @target macos, windows { node { font-size: 30px; } }\n}\n'
           'a "label"\n')
    small = text_width(src, "linux")
    assert text_width(src, "windows") > small * 2.5
    assert text_width(src, "macos") > small * 2.5
    assert text_width(src, None) == pytest.approx(small, rel=0.25)  # no target: block ignored


def test_platform_without_metric_copy_warns():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", FontWarning)
        with use_target("macos"):
            measure("x", '"Segoe UI", Comic, fantasy', 12)
    assert any("not" in str(w.message) or "no metric" in str(w.message) for w in caught)


def test_web_warns_about_unmeasurable_fonts():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", FontWarning)
        with use_target("web"):
            measure("x", '"Some Webfont", sans-serif', 12)
    assert any("Some Webfont".lower() in str(w.message) for w in caught)


def test_target_is_scoped_to_one_build():
    with use_target("windows"):
        pass
    a = node_width('graph\na "' + LONG + '"\n', "linux")
    b = node_width('graph\na "' + LONG + '"\n', "linux")
    assert a == b
