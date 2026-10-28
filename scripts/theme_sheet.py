#!/usr/bin/env python3
"""Render one .nod file in several themes and tile the results into one PNG."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


class ThemeSheet:
    def __init__(self, src: Path, themes: list[str], outdir: Path, scale: float):
        self.src, self.themes, self.outdir, self.scale = src, themes, outdir, scale

    def render(self, theme: str) -> Path:
        svg = self.outdir / f"{self.src.stem}-{theme}.svg"
        png = svg.with_suffix(".png")
        subprocess.run(["uv", "run", "-q", "nodal", str(self.src), "--theme", theme, "-o", str(svg)], check=True)
        subprocess.run(["uv", "run", "-q", "--with", "cairosvg", "cairosvg", str(svg), "-o", str(png),
                        "-s", str(self.scale)], check=True)
        print(png)
        return png

    def tile(self, pngs: list[Path], cols: int) -> Path:
        from PIL import Image, ImageDraw
        ims = [Image.open(p).convert("RGB") for p in pngs]
        w = max(i.width for i in ims)
        h = max(i.height for i in ims) + 30
        rows = (len(ims) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * w, rows * h), "#ffffff")
        d = ImageDraw.Draw(sheet)
        for k, (p, im) in enumerate(zip(pngs, ims)):
            x, y = (k % cols) * w, (k // cols) * h
            d.text((x + 10, y + 8), p.stem, fill="#000000")
            sheet.paste(im, (x, y + 30))
        out = self.outdir / f"{self.src.stem}-themes.png"
        sheet.save(out)
        print(out)
        return out

    def run(self, cols: int) -> None:
        self.outdir.mkdir(parents=True, exist_ok=True)
        pngs = [self.render(t) for t in self.themes]
        if len(pngs) > 1:
            self.tile(pngs, cols)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", type=Path)
    ap.add_argument("themes", nargs="+")
    ap.add_argument("--outdir", type=Path, default=None)
    ap.add_argument("--cols", type=int, default=2)
    ap.add_argument("--scale", type=float, default=1.5)
    a = ap.parse_args()
    ThemeSheet(a.src, a.themes, a.outdir or a.src.parent, a.scale).run(a.cols)
    return 0


if __name__ == "__main__":
    sys.exit(main())
