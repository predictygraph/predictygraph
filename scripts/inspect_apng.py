#!/usr/bin/env python3
"""Inspect an APNG: frame count, durations, and how much each frame differs from the first."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageSequence


class ApngInspector:
    def __init__(self, path: Path):
        self.path = path

    def run(self, dump: Path | None) -> None:
        im = Image.open(self.path)
        frames = [f.convert("RGBA").copy() for f in ImageSequence.Iterator(im)]
        durs = [f.info.get("duration") for f in ImageSequence.Iterator(Image.open(self.path))]
        print(f"{self.path}: {len(frames)} frames, size {frames[0].size}, loop={im.info.get('loop')}, "
              f"durations ms={sorted(set(durs))}")
        first = frames[0]
        diffs = [ImageChops.difference(first.convert("RGB"), f.convert("RGB")).getbbox() is not None for f in frames]
        print(f"frames differing from frame 0: {sum(diffs)}/{len(frames)}")
        if dump:
            dump.mkdir(parents=True, exist_ok=True)
            for k in (0, len(frames) // 3, 2 * len(frames) // 3):
                p = dump / f"frame_{k:03d}.png"
                frames[k].save(p)
                print(p)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", type=Path)
    ap.add_argument("--dump", type=Path, default=None, help="Write three sample frames here")
    a = ap.parse_args()
    ApngInspector(a.path).run(a.dump)
    return 0


if __name__ == "__main__":
    sys.exit(main())
