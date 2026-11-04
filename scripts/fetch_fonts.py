#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Reza Jelveh
#
# SPDX-License-Identifier: Apache-2.0
"""Fetch the metric fonts predictygraph bundles into src/predictygraph/fonts/.

DejaVu Sans (Linux default), Liberation Sans/Serif (same widths as Arial/Helvetica and
Times New Roman) and Carlito (same widths as Calibri). All are freely redistributable.
"""
import argparse
import io
import tarfile
import urllib.request
from pathlib import Path

SOURCES = {
    "https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.tar.bz2": {
        "ttf/DejaVuSans.ttf": "DejaVuSans.ttf",
        "ttf/DejaVuSans-Bold.ttf": "DejaVuSans-Bold.ttf",
        "dejavu-fonts-ttf-2.37/LICENSE": "LICENSE-DejaVu.txt",
    },
    "https://github.com/liberationfonts/liberation-fonts/files/7261482/liberation-fonts-ttf-2.1.5.tar.gz": {
        "LiberationSans-Regular.ttf": "LiberationSans-Regular.ttf",
        "LiberationSans-Bold.ttf": "LiberationSans-Bold.ttf",
        "LiberationSerif-Regular.ttf": "LiberationSerif-Regular.ttf",
        "LiberationSerif-Bold.ttf": "LiberationSerif-Bold.ttf",
        "LiberationMono-Regular.ttf": "LiberationMono-Regular.ttf",
        "LiberationMono-Bold.ttf": "LiberationMono-Bold.ttf",
    },
}
FILES = {
    "https://github.com/googlefonts/carlito/raw/main/fonts/ttf/Carlito-Regular.ttf": "Carlito-Regular.ttf",
    "https://github.com/googlefonts/carlito/raw/main/fonts/ttf/Carlito-Bold.ttf": "Carlito-Bold.ttf",
    "https://github.com/google/fonts/raw/main/ofl/roboto/OFL.txt": "LICENSE-Roboto.txt",
}
# Variable fonts: one download, pinned to fixed instances (name -> axis values).
VARIABLE = {
    "https://github.com/google/fonts/raw/main/ofl/roboto/Roboto%5Bwdth,wght%5D.ttf": {
        "Roboto-Regular.ttf": {"wght": 400, "wdth": 100},
        "Roboto-Bold.ttf": {"wght": 700, "wdth": 100},
    },
}


class FontFetcher:
    def __init__(self, out: Path):
        self.out = out
        out.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def get(url: str) -> bytes:
        with urllib.request.urlopen(url, timeout=60) as r:
            return r.read()

    def from_archive(self, url: str, wanted: dict[str, str]) -> None:
        with tarfile.open(fileobj=io.BytesIO(self.get(url))) as tar:
            for m in tar.getmembers():
                for suffix, name in wanted.items():
                    if m.isfile() and m.name.endswith(suffix):
                        (self.out / name).write_bytes(tar.extractfile(m).read())
                        print(name)

    def from_variable(self, url: str, instances: dict[str, dict[str, float]]) -> None:
        """Pin a variable font to fixed weights (needs fonttools), so widths match exactly."""
        from fontTools.ttLib import TTFont
        from fontTools.varLib.instancer import instantiateVariableFont
        data = self.get(url)
        for name, axes in instances.items():
            font = instantiateVariableFont(TTFont(io.BytesIO(data)), axes)
            font.save(str(self.out / name))
            print(name)

    def run(self) -> None:
        for url, wanted in SOURCES.items():
            self.from_archive(url, wanted)
        for url, name in FILES.items():
            (self.out / name).write_bytes(self.get(url))
            print(name)
        for url, instances in VARIABLE.items():
            self.from_variable(url, instances)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out", type=Path)
    FontFetcher(ap.parse_args().out).run()


if __name__ == "__main__":
    main()
