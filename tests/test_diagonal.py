from nodal.model import Document, Group
from nodal.svg import SvgRenderer


class _R(SvgRenderer):
    def __init__(self, diag_max=40.0, angle=45.0):
        super().__init__(Document(root=Group(id="__root__", kind="graph")))
        self._diag_max, self._diag_angle = diag_max, angle


def _segments(pts):
    out = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        out.append("v" if abs(x1 - x0) < 1e-6 else "h" if abs(y1 - y0) < 1e-6 else "d")
    return out


def test_aligned_is_one_straight_line():
    assert _R().octilinear((0, 0), (0, 100), "v", None, 10) == [(0, 0), (0, 100)]


def test_small_offset_with_room_goes_diagonal_at_45():
    pts = _R().octilinear((0, 0), (20, 100), "v", None, 10)
    assert _segments(pts) == ["v", "d", "v"]
    (ax, ay), (bx, by) = pts[1], pts[2]
    assert abs(abs(bx - ax) - abs(by - ay)) < 1e-6  # 45 degrees


def test_large_offset_goes_orthogonal():
    assert _segments(_R().octilinear((0, 0), (200, 100), "v", None, 10)) == ["v", "h", "v"]


def test_small_offset_without_room_goes_orthogonal():
    # 30px sideways needs 30px of run at 45 deg, but only 40 - 2*10 = 20px is free
    assert _segments(_R().octilinear((0, 0), (30, 40), "v", None, 10)) == ["v", "h", "v"]


def test_diagonal_none_and_steeper_angle():
    assert _segments(_R(diag_max=0).octilinear((0, 0), (20, 100), "v", None, 10)) == ["v", "h", "v"]
    pts = _R(angle=60).octilinear((0, 0), (20, 100), "v", None, 10)
    assert abs(pts[2][1] - pts[1][1]) < 20  # steeper slant uses less run than 45 deg


def test_horizontal_flow_and_bus_level():
    pts = _R().octilinear((0, 0), (100, 20), "h", 30.0, 10)
    assert _segments(pts) == ["h", "d", "h"]
    assert abs((pts[1][0] + pts[2][0]) / 2 - 30.0) < 1e-6  # slant centred on bus level
