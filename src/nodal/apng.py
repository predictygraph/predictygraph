"""Animated PNG export: render frames at fixed times, rasterise, stitch into an APNG."""
from __future__ import annotations

import io
from pathlib import Path

from .svg import loop_seconds, render_svg


class ApngExporter:
    def __init__(self, doc, fps: int = 20, scale: float = 2.0, seconds: float | None = None):
        self.doc, self.fps, self.scale = doc, fps, scale
        self.seconds = seconds or loop_seconds(doc) or 1.0

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
        return [self._raster(render_svg(self.doc, i / self.fps)) for i in range(n)]

    def save(self, out: Path) -> Path:
        frames = self.frames()
        ms = round(1000 / self.fps)
        frames[0].save(out, format="PNG", save_all=True, append_images=frames[1:],
                       duration=ms, loop=0, disposal=1, blend=0, default_image=False)
        return out
