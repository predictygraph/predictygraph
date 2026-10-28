#!/usr/bin/env python3
"""Debug: show router channels, needs and extra gaps per layout pass for a .nod file."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nodal import _style
from nodal.layout import layout
from nodal.parser import parse_file
from nodal.route import Router


class RouteDebug:
    def __init__(self, src: Path):
        self.doc = _style(parse_file(src), None, None)

    def run(self, passes: int) -> None:
        doc = self.doc
        for p in range(passes):
            layout(doc)
            r = Router(doc).route()
            ri = getattr(doc.root.layout_obj, "rank_index", None)
            print(f"pass {p}: rank_index={ri} extra={getattr(doc.root, 'extra_gap', {})}")
            for e in doc.edges:
                print(f"  {e.id} {e.src}->{e.dst} chan={r.channel.get(e.id)} gap={r.gapkey.get(e.id)} "
                      f"level={r.level(e)}")
            print(f"  needs={r.needs}")
            if not r.needs:
                break
            for (gid, rank), need in r.needs.items():
                g = doc.root if gid == doc.root.id else doc.items[gid]
                ex = getattr(g, "extra_gap", {})
                ex[rank] = ex.get(rank, 0.0) + need
                g.extra_gap = ex


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", type=Path)
    ap.add_argument("--passes", type=int, default=4)
    a = ap.parse_args()
    RouteDebug(a.src).run(a.passes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
