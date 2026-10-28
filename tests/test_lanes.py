import re

from nodal import render


def _levels(svg, eid):
    """Y of the horizontal run in a vertical-flow edge path."""
    body = svg.split(f'<g id="{eid}"', 1)[1].split("</g>", 1)[0]
    d = re.search(r' d="([^"]+)"', body)[1]
    pairs = [(float(x), float(y)) for x, y in re.findall(r"([\d.]+) ([\d.]+)", d)]
    runs = [p[1] for p, q in zip(pairs, pairs[1:]) if p[1] == q[1] and p[0] != q[0]]
    return runs[0] if runs else None


SRC = '''graph dir=TB route=bend diagonal=none
group top layout=row gap=60 { a; b; m; c }
t
a -> t
b ..> t
c -> t
m -> t constraint=false
'''


def test_distinct_traces_into_same_node_get_separate_lanes():
    svg = render(SRC)
    la, lb = _levels(svg, "e0"), _levels(svg, "e1")
    assert la is not None and lb is not None
    assert abs(la - lb) >= 6  # solid and dashed "later" path do not share a run


def test_same_style_fan_in_still_merges_into_bus():
    svg = render(SRC.replace("b ..> t", "b -> t"))
    assert _levels(svg, "e0") == _levels(svg, "e1")
