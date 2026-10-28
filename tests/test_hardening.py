"""Hardening: number parsing, var() expansion, path confinement, limits."""
import pytest

from nodal import NodalSyntaxError, build_scene, parse, render
from nodal.anim import Track, dash_len, seconds
from nodal.safe import MAX_VAR_LEN, UnsafePathError
from nodal.style import StyleSheet, px


@pytest.mark.parametrize("v,want", [(".", 0.0), ("1.2.3", 1.2), ("-.5px", -0.5), ("1e999", 1e6), ("abc", 0.0)])
def test_px_never_raises(v, want):
    assert px(v) == want


def test_seconds_and_dash_bad_input():
    assert seconds(".") == 1.0
    assert seconds("1e9") == 3600.0
    assert dash_len("4 .") == 8.0


def test_track_degenerate():
    assert Track("x", [3.0], 0).at(5) == 3.0


def test_bad_numbers_render():
    render('a -> b width=. "x"\n')
    render('a "x" font-size=' + "9" * 400 + "\n")
    render("css { edge { stroke-dasharray: 4 .; flow: forward; flow-speed: .; } }\na -> b\n")


def test_var_expansion_is_bounded():
    s = StyleSheet()
    chain = "".join(f"--{c}:" + f"var(--{p}) " * 20 + ";" for p, c in zip("abcdefg", "bcdefgh"))
    s.add(":root{--a:x;" + chain + "}")
    assert len(s.resolve_vars({"fill": "var(--h)"})["fill"]) <= MAX_VAR_LEN


def test_nested_var_fallback():
    s = StyleSheet()
    s.add(":root{--y:red}")
    assert s.resolve_vars({"fill": "var(--x, var(--y))"})["fill"] == "red"


@pytest.mark.parametrize("src", ["a image=/etc/hostname\n", "a image=../../../../etc/hostname\n",
                                 'css "/etc/hostname"\na\n'])
def test_paths_confined(src, tmp_path):
    with pytest.raises(UnsafePathError):
        build_scene(parse(src, str(tmp_path)))


def test_allow_outside(tmp_path):
    (tmp_path / "s.css").write_text("node { fill: #123456; }")
    sub = tmp_path / "d"
    sub.mkdir()
    assert "#123456" in render('css "../s.css"\na\n', str(sub), allow_outside=True)


def test_edge_cap():
    side = ",".join(f"n{i}" for i in range(101))
    with pytest.raises(NodalSyntaxError, match="too many edges"):
        parse(f"{side} -> {side}\n")


def test_overlong_arrow_rejected():
    with pytest.raises(NodalSyntaxError):
        parse("a " + "-" * 50000 + "> b\n")


def test_css_block_tail_kept():
    doc = parse("css { node { fill: red; } } a -> b\n")
    assert len(doc.edges) == 1
