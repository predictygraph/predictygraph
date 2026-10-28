"""Animation tracks: format-independent keyframe descriptions.

Every animated property is a looping linear keyframe track ``(attr, values, dur)``
attached to a Scene IR element. The first keyframe always equals the static value, so
writers that cannot animate (PDF, PNG, ODP) just use it. Writers that can animate
(SVG via SMIL) emit the track; frame writers (APNG) sample it with ``Track.at(t)``.
"""
from __future__ import annotations

import math
import re

from .safe import NUM, numbers

FLOW_MODES = ("forward", "reverse", "both", "auto")
BORDER_MODES = ("march", "pulse", "glow")


def seconds(v, default: float = 1.0) -> float:
    if v is None:
        return default
    m = re.match(rf"\s*({NUM})\s*(ms|s)?\s*$", str(v))
    if not m:
        return default
    n = float(m.group(1))
    n = n / 1000 if m.group(2) == "ms" else n
    return min(3600.0, max(0.05, n)) if n == n else default


def dash_len(dash: str) -> float:
    nums = [abs(x) for x in numbers(dash)]
    if not nums:
        return 0.0
    if len(nums) % 2:
        nums = nums * 2  # SVG repeats odd-length dash lists
    return sum(nums)


class Track:
    """A looping linear keyframe track over evenly spaced keyframes."""

    def __init__(self, attr: str, values: list[float], dur: float):
        if not values:
            raise ValueError("track needs at least one value")
        values = values if len(values) > 1 else values * 2
        dur = dur if dur > 0 else 1.0
        self.attr, self.values, self.dur = attr, values, dur

    def at(self, t: float) -> float:
        vs = self.values
        ph = (t % self.dur) / self.dur * (len(vs) - 1)
        i = min(int(ph), len(vs) - 2)
        f = ph - i
        return vs[i] + (vs[i + 1] - vs[i]) * f

    def shifted(self, delta: float) -> "Track":
        return Track(self.attr, [v + delta for v in self.values], self.dur)


def flow_tracks(dash: str, dur: float, reverse: bool) -> list[Track]:
    L = dash_len(dash) or 10.0
    # offset L -> 0 moves the dash pattern towards the path's end
    return [Track("stroke-dashoffset", [0.0, L] if reverse else [L, 0.0], dur)]


def border_tracks(mode: str, sw: float, dash: str | None, dur: float) -> list[Track]:
    if mode == "march":
        return [Track("stroke-dashoffset", [dash_len(dash) or 10.0, 0.0], dur)]
    if mode == "pulse":
        return [Track("stroke-opacity", [1.0, 0.35, 1.0], dur),
                Track("stroke-width", [sw, sw * 2.2, sw], dur)]
    if mode == "glow":  # applied to a halo copy behind the shape
        return [Track("stroke-width", [sw, sw + 10, sw + 10], dur),
                Track("stroke-opacity", [0.7, 0.0, 0.0], dur)]
    return []


def loop_length(durations: list[float], cap: float = 12.0) -> float:
    """Shortest time after which every track is back at its start (LCM on a 10 ms grid)."""
    if not durations:
        return 1.0
    l = 1
    for d in durations:
        c = max(1, round(d * 100))
        l = l * c // math.gcd(l, c)
    lcm = l / 100
    return lcm if lcm <= cap else min(max(durations), cap)
