# SPDX-FileCopyrightText: 2026 The predictygraph Authors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Pick the font file used to measure a label, for a given render target.

Text is measured to size boxes, but drawn later by whatever displays the SVG. If the two
use different fonts, labels overflow or leave gaps. A *target* says where the SVG will be
shown, so we can measure with the font that viewer will actually use:

- ``linux`` / ``macos`` / ``windows``: the first font in the CSS list that this platform ships.
- ``web``: every font in the list; boxes are sized for the widest, so any choice fits.
- ``host`` (default when no target is set): whatever this machine resolves via fontconfig.

Bundled metric fonts (no outlines, widths and kerning only) stand in for common fonts,
including proprietary ones with identical widths (Liberation Sans = Arial/Helvetica,
Liberation Serif = Times New Roman, Carlito = Calibri).
"""
from __future__ import annotations

import functools
import subprocess
import warnings
from dataclasses import dataclass
from pathlib import Path

BUNDLED = Path(__file__).parent / "fonts"

# family (lower case) -> bundled file stem (regular, bold)
METRIC = {
    "dejavu sans": ("DejaVuSans", "DejaVuSans-Bold"),
    "liberation sans": ("LiberationSans-Regular", "LiberationSans-Bold"),
    "liberation serif": ("LiberationSerif-Regular", "LiberationSerif-Bold"),
    "liberation mono": ("LiberationMono-Regular", "LiberationMono-Bold"),
    "carlito": ("Carlito-Regular", "Carlito-Bold"),
}
# Proprietary or common fonts with identical advance widths to a bundled one.
ALIASES = {
    "arial": "liberation sans", "helvetica": "liberation sans", "helvetica neue": "liberation sans",
    "arimo": "liberation sans",
    "times new roman": "liberation serif", "times": "liberation serif", "tinos": "liberation serif",
    "courier new": "liberation mono", "courier": "liberation mono", "cousine": "liberation mono",
    "calibri": "carlito",
    "bitstream vera sans": "dejavu sans", "verdana": "dejavu sans",
}

# Fonts each platform ships, and what the generic CSS families resolve to there.
PLATFORMS = {
    "linux": {
        "has": {"dejavu sans", "liberation sans", "liberation serif", "liberation mono", "carlito"},
        "generic": {"sans-serif": "dejavu sans", "serif": "liberation serif", "monospace": "liberation mono",
                    "system-ui": "dejavu sans"},
    },
    "macos": {
        "has": {"helvetica", "helvetica neue", "arial", "times", "times new roman", "courier", "courier new",
                "verdana"},
        "generic": {"sans-serif": "helvetica", "serif": "times", "monospace": "courier",
                    "system-ui": "helvetica neue"},
    },
    "windows": {
        "has": {"arial", "times new roman", "courier new", "calibri", "verdana"},
        "generic": {"sans-serif": "arial", "serif": "times new roman", "monospace": "courier new",
                    "system-ui": "arial"},
    },
}
TARGETS = ("host", "web", *PLATFORMS)
GENERIC = {"sans-serif", "serif", "monospace", "system-ui", "cursive", "fantasy", "ui-sans-serif"}


class FontWarning(UserWarning):
    """A requested font could not be measured exactly; widths may not match the viewer."""


def families(css: str) -> list[str]:
    """CSS font-family list -> lower-case names, quotes stripped."""
    out = [f.strip().strip("\"'").strip().lower() for f in (css or "").split(",")]
    return [f for f in out if f and not f.startswith("-")] or ["sans-serif"]


@dataclass(frozen=True)
class FontChoice:
    path: str | None      # file to measure with; None = Pillow's built-in default
    family: str           # the family the viewer is expected to draw with
    exact: bool           # True if widths are known to match that family


def bundled(family: str, bold: bool) -> str | None:
    key = ALIASES.get(family, family)
    stems = METRIC.get(key)
    if not stems:
        return None
    p = BUNDLED / f"{stems[1 if bold else 0]}.ttf"
    return str(p) if p.exists() else None


@functools.lru_cache(maxsize=64)
def fontconfig(family: str, bold: bool) -> tuple[str | None, str | None]:
    """(file, resolved family) from fc-match, or (None, None) without fontconfig."""
    pattern = family + (":bold" if bold else "")
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}\t%{family[0]}", "--", pattern],
                             capture_output=True, text=True, timeout=5, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None, None
    path, _, fam = out.partition("\t")
    return (path or None), (fam.lower() or None)


class FontResolver:
    def __init__(self, target: str = "host"):
        if target not in TARGETS:
            raise ValueError(f"unknown target {target!r} (choose from: {', '.join(TARGETS)})")
        self.target = target
        self.warned: set[str] = set()

    def warn(self, msg: str) -> None:
        if msg not in self.warned:
            self.warned.add(msg)
            warnings.warn(msg, FontWarning, stacklevel=4)

    def platform(self, name: str, fams: list[str], bold: bool) -> FontChoice:
        plat = PLATFORMS[name]
        for fam in fams:
            fam = plat["generic"].get(fam, fam)
            if fam in plat["has"]:
                path = bundled(fam, bold)
                if path:
                    return FontChoice(path, fam, True)
                return self.approximate(fam, bold, f"{name} ships {fam!r}, but predictygraph has no metric copy")
        return self.approximate(fams[0], bold, f"none of {fams} is available on {name}")

    def approximate(self, fam: str, bold: bool, why: str) -> FontChoice:
        """Widest bundled sans as a safe stand-in (text then fits, possibly with spare room)."""
        self.warn(f"font {fam!r}: {why}; measuring with DejaVu Sans, labels may not fit exactly")
        return FontChoice(bundled("dejavu sans", bold), fam, False)

    def host(self, fams: list[str], bold: bool) -> FontChoice:
        for fam in fams:
            if fam in GENERIC:
                path, got = fontconfig(fam, bold)
                return FontChoice(path, got or fam, path is not None)
            path, got = fontconfig(fam, bold)
            if path and got == fam:
                return FontChoice(path, fam, True)
            if (b := bundled(fam, bold)):
                return FontChoice(b, fam, True)
        path, got = fontconfig(fams[0], bold)
        self.warn(f"font {fams[0]!r} is not installed; measuring with {got or 'a default font'} instead. "
                  f"Set a target (e.g. --target web) or install the font")
        return FontChoice(path, got or fams[0], False)

    @functools.lru_cache(maxsize=256)
    def choose(self, css_family: str, bold: bool) -> list[FontChoice]:
        """Fonts to measure with; the caller takes the widest result."""
        fams = families(css_family)
        if self.target == "host":
            return [self.host(fams, bold)]
        if self.target in PLATFORMS:
            return [self.platform(self.target, fams, bold)]
        # web: any font in the list may be used by some browser; generic families mean "anything"
        out = [FontChoice(bundled(f, bold), f, True) for f in fams if bundled(f, bold)]
        unknown = [f for f in fams if not bundled(f, bold) and f not in GENERIC]
        for f in unknown:
            self.warn(f"font {f!r} has no metric copy; web target sizes boxes without it")
        if any(f in GENERIC for f in fams) or not out:
            out += [FontChoice(bundled(f, bold), f, True) for f in ("dejavu sans", "liberation sans")]
        return out
