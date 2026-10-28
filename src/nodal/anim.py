"""Animation support: one description, two outputs.

Every animated property is a looping keyframe track ``(attr, values, dur)``.

* Animated SVG (``t is None``): the base attribute is the first keyframe (so static
  renderers show a complete diagram) and a SMIL ``<animate>`` child drives it.
* Frame at time ``t`` (APNG / stills): the value is interpolated and written as a
  plain attribute, no SMIL. Frames are rasterised and stitched into an APNG.
"""
from __future__ import annotations

import math
import re

FLOW_MODES = ("forward", "reverse", "both", "auto")
BORDER_MODES = ("march", "pulse", "glow")


def seconds(v, default: float = 1.0) -> float:
    if v is None:
        return default
    m = re.match(r"\s*([\d.]+)\s*(ms|s)?\s*$", str(v))
    if not m:
        return default
    n = float(m.group(1))
    return max(0.05, n / 1000 if m.group(2) == "ms" else n)


def dash_len(dash: str) -> float:
    nums = [float(x) for x in re.findall(r"[\d.]+", dash or "")]
    if not nums:
        return 0.0
    if len(nums) % 2:
        nums = nums * 2  # SVG repeats odd-length dash lists
    return sum(nums)


class Track:
    """A looping linear keyframe track over evenly spaced keyframes."""

    def __init__(self, attr: str, values: list[float], dur: float):
        self.attr, self.values, self.dur = attr, values, dur

    def at(self, t: float) -> float:
        vs = self.values
        ph = (t % self.dur) / self.dur * (len(vs) - 1)
        i = min(int(ph), len(vs) - 2)
        f = ph - i
        return vs[i] + (vs[i + 1] - vs[i]) * f

    def smil(self) -> str:
        vals = ";".join(f"{v:g}" for v in self.values)
        return (f'<animate attributeName="{self.attr}" values="{vals}" dur="{self.dur:g}s" '
                f'repeatCount="indefinite"/>')


class Animator:
    """Collects tracks per element and emits either SMIL or frame values."""

    def __init__(self, t: float | None):
        self.t = t
        self.durations: list[float] = []

    @property
    def animated(self) -> bool:
        return self.t is None

    def apply(self, tracks: list[Track]) -> tuple[dict[str, str], str]:
        """-> (attribute overrides, SMIL children)."""
        attrs, kids = {}, []
        for tr in tracks:
            self.durations.append(tr.dur)
            v = tr.values[0] if self.t is None else tr.at(self.t)
            attrs[tr.attr] = f"{v:.2f}".rstrip("0").rstrip(".") or "0"
            if self.t is None:
                kids.append(tr.smil())
        return attrs, "".join(kids)

    # ---- presets --------------------------------------------------------
    @staticmethod
    def flow_tracks(dash: str, dur: float, reverse: bool) -> list[Track]:
        L = dash_len(dash) or 10.0
        # offset L -> 0 moves the dash pattern towards the path's end
        return [Track("stroke-dashoffset", [0.0, L] if reverse else [L, 0.0], dur)]

    @staticmethod
    def border_tracks(mode: str, sw: float, dash: str, dur: float) -> list[Track]:
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


def inject(elem: str, attrs: dict[str, str], kids: str) -> str:
    """Override attributes on the first tag of `elem` and append SMIL children to it."""
    m = re.match(r"\s*<(\w+)([^>]*?)(/?)>", elem)
    if not m:
        return elem
    tag, body, selfclose = m.group(1), m.group(2), m.group(3)
    for k, v in attrs.items():
        if re.search(rf'\s{re.escape(k)}="[^"]*"', body):
            body = re.sub(rf'(\s{re.escape(k)}=")[^"]*(")', rf"\g<1>{v}\g<2>", body)
        else:
            body += f' {k}="{v}"'
    rest = elem[m.end():]
    if selfclose:
        return f"<{tag}{body}>{kids}</{tag}>" + rest if kids else f"<{tag}{body}/>" + rest
    return f"<{tag}{body}>{kids}" + rest
