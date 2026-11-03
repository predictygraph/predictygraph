# SPDX-FileCopyrightText: 2026 The predictygraph Authors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Small style readers shared by layout (sizing) and scene (drawing), so both sides
agree on what a style means: text metrics, accent bars, header bands, title position."""
from __future__ import annotations

from .style import box4, px
from .text import measure

BOLD = ("bold", "bolder", "600", "700", "800", "900")
LINE_H = 1.25  # line height as a multiple of the font size (matches SceneBuilder.text)


def font_size(st: dict, default: float) -> float:
    return px(st.get("font-size"), default)


def is_bold(st: dict, default: bool = False) -> bool:
    w = st.get("font-weight")
    return default if w is None else w in BOLD


def text_block(text: str | None, st: dict, default_fs: float,
               bold: bool | None = None) -> tuple[float, float, list[str]]:
    """(width, height, lines) of `text` in style `st`; zeros for empty text.
    `bold` overrides the style's weight (step numbers, legend titles)."""
    if not text:
        return 0.0, 0.0, []
    return measure(text, st.get("font-family", "sans-serif"), font_size(st, default_fs),
                   is_bold(st) if bold is None else bold)


def accent(st: dict) -> tuple[float, str | None, str] | None:
    """`accent-bar: 4px #16a34a` -> (width, colour or None, side); None when off."""
    spec = (st.get("accent-bar") or "").split()
    if not spec or spec[0] == "none":
        return None
    return px(spec[0], 4), (spec[1] if len(spec) > 1 else None), st.get("accent-side", "left")


def accent_width(st: dict, side: str) -> float:
    """Room an accent bar takes on `side` (inside the box, before the padding)."""
    a = accent(st)
    return a[0] if a and a[2] == side else 0.0


def node_padding(st: dict) -> tuple[float, float, float, float]:
    """A node's (top, right, bottom, left) padding, widened by its accent bar."""
    pt, pr, pb, pl = box4(st.get("padding"), 8)
    return pt, pr + accent_width(st, "right"), pb, pl + accent_width(st, "left")


def title_position(st: dict) -> str:
    return st.get("label-position", "top")


def has_title_band(st: dict) -> bool:
    """`title-fill` draws a band behind a top title only."""
    return st.get("title-fill") not in (None, "none") and title_position(st) == "top"
