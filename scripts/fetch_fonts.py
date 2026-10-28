#!/usr/bin/env python3
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

    def run(self) -> None:
        for url, wanted in SOURCES.items():
            self.from_archive(url, wanted)
        for url, name in FILES.items():
            (self.out / name).write_bytes(self.get(url))
            print(name)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out", type=Path)
    FontFetcher(ap.parse_args().out).run()


if __name__ == "__main__":
    main()
