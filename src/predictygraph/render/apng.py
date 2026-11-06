# SPDX-FileCopyrightText: 2026 Reza Jelveh
#
# SPDX-License-Identifier: Apache-2.0

"""PNG / APNG writer: Scene IR -> PNG (one frame) or animated PNG (frames sampled from
the animation tracks).

Size controls: `scale` (pixel scale) or `width` (target pixel width, overrides scale);
`still` forces one frame; `colors` quantises to a palette (much smaller files for flat
diagram colours). A scene without animation is always written as a single frame.
"""

from __future__ import annotations

import io
from pathlib import Path

from ..anim import loop_length
from ..ir import Scene
from .svg import write_svg

MAX_PIXELS = 8000  # longest side; keeps a typo in --width/--scale from eating memory


class ApngWriter:
    def __init__(
        self,
        scene: Scene,
        fps: int = 20,
        scale: float = 2.0,
        seconds: float | None = None,
        width: int | None = None,
        still: bool = False,
        colors: int | None = None,
    ):
        self.scene, self.fps = scene, fps
        if width:
            scale = width / max(scene.width, 1.0)
        longest = max(scene.width, scene.height, 1.0)
        self.scale = max(0.05, min(scale, MAX_PIXELS / longest))
        durs = scene.durations()
        self.still = still or not durs
        self.seconds = seconds or (loop_length(durs) if durs else 1.0)
        self.colors = max(2, min(int(colors), 256)) if colors else None

    def _raster(self, svg: str):
        try:
            import cairosvg
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("PNG export needs cairosvg: install predictygraph[apng]") from exc
        from PIL import Image

        png = cairosvg.svg2png(bytestring=svg.encode(), scale=self.scale)
        return Image.open(io.BytesIO(png)).convert("RGBA")

    def frames(self):
        n = 1 if self.still else max(1, round(self.seconds * self.fps))
        return [self._raster(write_svg(self.scene, i / self.fps)) for i in range(n)]

    def _flatten(self, im):
        """Opaque RGB (diagrams have a background) and, with `colors`, a palette image."""
        from PIL import Image

        bg = Image.new("RGBA", im.size, self.scene.background or "#ffffff")
        rgb = Image.alpha_composite(bg, im).convert("RGB")
        if self.colors:
            return rgb.quantize(self.colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        return rgb

    def save(self, out: Path) -> Path:
        frames = [self._flatten(f) for f in self.frames()]
        if len(frames) == 1:
            frames[0].save(out, format="PNG", optimize=True)
        else:
            frames[0].save(
                out,
                format="PNG",
                save_all=True,
                append_images=frames[1:],
                duration=round(1000 / self.fps),
                loop=0,
                disposal=1,
                blend=0,
                default_image=False,
                optimize=True,
            )
        return out


def write_apng(
    scene: Scene,
    out: Path,
    fps: int = 20,
    scale: float = 2.0,
    seconds: float | None = None,
    width: int | None = None,
    still: bool = False,
    colors: int | None = None,
) -> Path:
    return ApngWriter(scene, fps, scale, seconds, width, still, colors).save(out)
