# SPDX-FileCopyrightText: 2026 Reza Jelveh
#
# SPDX-License-Identifier: Apache-2.0

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


def test_png_width_colors_and_single_frame(tmp_path):
    import pytest
    pytest.importorskip("cairosvg")  # optional extra: predictygraph[apng]
    pytest.importorskip("PIL")
    from PIL import Image
    from predictygraph.render.apng import write_apng
    sc = build_scene(parse('a "x"\nb "y"\na -> b\n'))
    out = write_apng(sc, tmp_path / "d.png", width=300, colors=16)
    im = Image.open(out)
    assert im.size[0] == 300 and getattr(im, "n_frames", 1) == 1 and im.mode == "P"


def test_align_x_lines_up_across_panels():
    src = ('graph layout=column align=stretch\n'
           'group top layout=row gap=20 {\n a "left box"\n b "short"\n}\n'
           'group bottom layout=row gap=200 {\n c "c"\n d "a much wider box here"\n}\n')
    plain = parse(src)
    build_scene(plain)
    doc = parse(src.replace('b "short"', 'b "short" align-x=d'))
    build_scene(doc)
    assert abs(doc.items["b"].cx - doc.items["d"].cx) < 0.5
    assert abs(plain.items["b"].cx - plain.items["d"].cx) > 1  # it really moved


def test_align_x_stays_inside_its_panel():
    src = ('graph layout=column\n'
           'group top layout=row gap=20 {\n a "left box"\n b "short" align-x=d\n}\n'
           'group bottom layout=row gap=400 {\n c "c"\n d "far right"\n}\n')
    doc = parse(src)
    build_scene(doc)
    b, top = doc.items["b"], doc.items["top"]
    assert b.ax + b.w <= top.ax + top.w


def test_align_x_never_overlaps_a_sibling():
    src = ('graph layout=column\n'
           'group top layout=row gap=10 {\n a "aaaaaaaa" align-x=z\n b "bbbbbbbb"\n}\n'
           'group bottom layout=row {\n y "y"\n z "z"\n}\n')
    doc = parse(src)
    build_scene(doc)
    a, b = doc.items["a"], doc.items["b"]
    assert a.ax + a.w <= b.ax


def test_accent_bar_stays_inside_rounded_corners():
    from predictygraph.scene import accent_segs
    segs = accent_segs(0, 0, 100, 40, 4, 10, "left")
    xs = [s[-2] for s in segs if s[0] != "Z"]
    ys = [s[-1] for s in segs if s[0] != "Z"]
    assert min(xs) >= 0 and max(xs) <= 4
    assert min(ys) > 0 and max(ys) < 40  # starts below the top edge: it follows the arc
    right = accent_segs(0, 0, 100, 40, 4, 10, "right")
    assert min(s[-2] for s in right if s[0] != "Z") >= 96


def test_align_x_keeps_gaps_by_moving_neighbours():
    src = ('graph layout=column align=stretch\n'
           'group top layout=row gap=300 {\n p "p"\n q "q"\n}\n'
           'group bottom layout=row gap=30 {\n a "aaaa" align-x=q\n b "bbbb"\n}\n'
           'a -> b "a fairly long label"\n')
    plain = parse(src.replace(" align-x=q", ""))
    build_scene(plain)
    doc = parse(src)
    build_scene(doc)
    gap = lambda d: d.items["b"].ax - (d.items["a"].ax + d.items["a"].w)
    assert abs(gap(doc) - gap(plain)) < 0.01  # b moved with a: the label still fits
    assert doc.items["a"].ax > plain.items["a"].ax
