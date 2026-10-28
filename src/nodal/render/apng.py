"""APNG writer: Scene IR -> animated PNG (frames sampled from the animation tracks)."""
from __future__ import annotations

import io
from pathlib import Path

from ..anim import loop_length
from ..ir import Scene
from .svg import write_svg


class ApngWriter:
    def __init__(self, scene: Scene, fps: int = 20, scale: float = 2.0, seconds: float | None = None):
        self.scene, self.fps, self.scale = scene, fps, scale
        durs = scene.durations()
        self.seconds = seconds or (loop_length(durs) if durs else 1.0)

    def _raster(self, svg: str):
        try:
            import cairosvg
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("APNG export needs cairosvg: install nodal[apng]") from exc
        from PIL import Image
        png = cairosvg.svg2png(bytestring=svg.encode(), scale=self.scale)
        return Image.open(io.BytesIO(png)).convert("RGBA")

    def frames(self):
        n = max(1, round(self.seconds * self.fps))
        return [self._raster(write_svg(self.scene, i / self.fps)) for i in range(n)]

    def save(self, out: Path) -> Path:
        frames = self.frames()
        frames[0].save(out, format="PNG", save_all=True, append_images=frames[1:],
                       duration=round(1000 / self.fps), loop=0, disposal=1, blend=0, default_image=False)
        return out


def write_apng(scene: Scene, out: Path, fps: int = 20, scale: float = 2.0, seconds: float | None = None) -> Path:
    return ApngWriter(scene, fps, scale, seconds).save(out)
