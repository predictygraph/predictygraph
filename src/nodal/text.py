"""Text measurement with real font files via Pillow, and image leaf loading."""
from __future__ import annotations

import base64
import functools
import mimetypes
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageFont

from .safe import NUM, number, safe_path

MAX_FONT = 1000.0


@functools.lru_cache(maxsize=64)
def find_font(family: str, bold: bool) -> str | None:
    fam = family.split(",")[0].strip().strip("\"'") or "sans-serif"
    fam = fam.lstrip("-") or "sans-serif"  # never let a family look like an fc-match option
    pattern = fam + (":bold" if bold else "")
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", "--", pattern], capture_output=True,
                             text=True, timeout=5, check=False).stdout.strip()
        return out or None
    except (OSError, subprocess.SubprocessError):
        return None


@functools.lru_cache(maxsize=256)
def get_font(family: str, size: float, bold: bool):
    size = min(MAX_FONT, max(1.0, size)) if size == size else 14.0
    path = find_font(family, bold)
    try:
        if path:
            return ImageFont.truetype(path, max(1, round(size)))
    except OSError:
        pass
    return ImageFont.load_default(size=size)


def measure(text: str, family: str, size: float, bold: bool = False) -> tuple[float, float, list[str]]:
    lines = text.split("\n") if text else []
    if not lines:
        return 0.0, 0.0, []
    size = min(MAX_FONT, max(1.0, size)) if size == size else 14.0
    font = get_font(family, size, bold)
    w = max(font.getlength(line) for line in lines)
    line_h = size * 1.25
    return w, line_h * len(lines), lines


def load_image(path: str, base_dir: str, allow_outside: bool = False) -> dict:
    p = safe_path(base_dir, path, allow_outside)
    data = p.read_bytes()
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    if p.suffix.lower() == ".svg":
        text = data.decode("utf-8", "replace")
        w = h = None
        m = re.search(rf'viewBox\s*=\s*"\s*{NUM}[\s,]+{NUM}[\s,]+({NUM})[\s,]+({NUM})', text)
        if m:
            w, h = number(m.group(1), 0, 0), number(m.group(2), 0, 0)
        else:
            mw = re.search(rf'<svg[^>]*\swidth="({NUM})', text)
            mh = re.search(rf'<svg[^>]*\sheight="({NUM})', text)
            if mw and mh:
                w, h = number(mw.group(1), 0, 0), number(mh.group(1), 0, 0)
        w, h = w or 64.0, h or 64.0
        mime = "image/svg+xml"
    else:
        with Image.open(p) as im:
            w, h = im.size
    return {"href": f"data:{mime};base64,{base64.b64encode(data).decode()}", "w": float(w), "h": float(h)}
