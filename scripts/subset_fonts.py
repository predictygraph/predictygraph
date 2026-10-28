#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 The predictygraph Authors
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shrink the bundled fonts to metric-only files so the repo stays small.

Keeps Latin, punctuation and arrows, with advance widths, kerning and layout features, so
measured widths match browsers. Glyph outlines are removed: these files measure text, they
never draw it. Labels outside these ranges fall back to the system font (with a warning).
"""
import argparse
from pathlib import Path

from fontTools import subset

UNICODES = "U+0020-007E,U+00A0-024F,U+0300-036F,U+2000-206F,U+20A0-20CF,U+2100-214F,U+2190-21FF,U+2200-22FF,U+2500-257F,U+25A0-25FF"


class FontSubsetter:
    def __init__(self, folder: Path):
        self.folder = folder

    def subset(self, path: Path) -> None:
        before = path.stat().st_size
        opts = subset.Options()
        opts.layout_features = ["*"]
        opts.name_IDs = ["*"]
        opts.name_languages = ["*"]
        opts.notdef_outline = True
        opts.glyph_names = False
        font = subset.load_font(str(path), opts)
        sub = subset.Subsetter(opts)
        sub.populate(unicodes=subset.parse_unicodes(UNICODES))
        sub.subset(font)
        self.strip_outlines(font)
        subset.save_font(font, str(path), opts)
        print(f"{path.name}: {before // 1024} KB -> {path.stat().st_size // 1024} KB")

    @staticmethod
    def strip_outlines(font) -> None:
        """Measurement needs advance widths and kerning, not shapes: empty every glyph."""
        if "glyf" not in font:
            return
        from fontTools.ttLib.tables._g_l_y_f import Glyph
        glyf = font["glyf"]
        for name in glyf.keys():
            glyf[name] = Glyph()
        for tag in ("hdmx", "LTSH", "VDMX", "fpgm", "prep", "cvt ", "gasp"):
            if tag in font:
                del font[tag]

    def run(self) -> None:
        for p in sorted(self.folder.glob("*.ttf")):
            self.subset(p)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", type=Path)
    FontSubsetter(ap.parse_args().folder).run()


if __name__ == "__main__":
    main()
