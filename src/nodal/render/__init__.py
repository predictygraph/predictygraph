"""Output handlers. Each one consumes a Scene IR and knows nothing about the DSL.

    svg   animated (SMIL) or frozen SVG
    apng  animated PNG, frames sampled from the scene's animation tracks
"""
from __future__ import annotations

from .apng import write_apng
from .svg import write_svg

WRITERS = {"svg": write_svg, "apng": write_apng}

__all__ = ["WRITERS", "write_svg", "write_apng"]
