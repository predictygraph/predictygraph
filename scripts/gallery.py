#!/usr/bin/env python3
"""Render every .nod in a folder to SVG + PNG and build a contact sheet."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


class Gallery:
    def __init__(self, folder: Path, scale: float):
        self.folder = folder
        self.scale = scale

    def render_one(self, src: Path) -> Path | None:
        svg = src.with_suffix(".svg")
        png = src.with_suffix(".png")
        r = subprocess.run(["uv", "run", "-q", "nodal", str(src), "-o", str(svg)],
                           capture_output=True, text=True, check=False)
        if r.returncode:
            print(f"FAIL {src.name}: {r.stderr.strip()}", file=sys.stderr)
            return None
        subprocess.run(["uv", "run", "-q", "--with", "cairosvg", "cairosvg", str(svg), "-o", str(png),
                        "-s", str(self.scale)], check=True)
        print(f"ok   {src.name}")
        return png

    def sheet(self, pngs: list[Path], out: Path) -> None:
        from PIL import Image, ImageDraw
        ims = [(p, Image.open(p).convert("RGB")) for p in pngs]
        cell_w = 900
        rows = []
        for p, im in ims:
            s = min(1.0, cell_w / im.width, 600 / im.height)
            rows.append((p, im.resize((int(im.width * s), int(im.height * s)))))
        cols = 2
        heights = [max(r[1].height for r in rows[i:i + cols]) + 40 for i in range(0, len(rows), cols)]
        sheet = Image.new("RGB", (cols * (cell_w + 20) + 20, sum(heights) + 20), "#d4d4d8")
        d = ImageDraw.Draw(sheet)
        y = 20
        for ri, h in enumerate(heights):
            for ci, (p, im) in enumerate(rows[ri * cols:(ri + 1) * cols]):
                x = 20 + ci * (cell_w + 20)
                d.text((x, y), p.stem, fill="#111")
                sheet.paste(im, (x, y + 18))
            y += h
        sheet.save(out)
        print(out)

    def run(self) -> int:
        pngs = [p for p in (self.render_one(s) for s in sorted(self.folder.glob("*.nod"))) if p]
        if pngs:
            self.sheet(pngs, self.folder / "gallery.png")
        return 0 if len(pngs) == len(list(self.folder.glob("*.nod"))) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--scale", type=float, default=2.0)
    a = ap.parse_args()
    return Gallery(a.folder, a.scale).run()


if __name__ == "__main__":
    sys.exit(main())
