"""Input hardening shared by the parser, styles, text and animation code."""
from __future__ import annotations

import re
from pathlib import Path

NUM = r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
NUM_RE = re.compile(NUM)
MAX_NUM = 1e6
MAX_EDGES = 10_000
MAX_VAR_LEN = 10_000


class UnsafePathError(ValueError):
    pass


def number(v, default: float = 0.0, lo: float = -MAX_NUM, hi: float = MAX_NUM) -> float:
    """Leading CSS-ish number of v, clamped to [lo, hi]; default when absent or not finite."""
    m = re.match(rf"\s*({NUM})", str(v)) if v is not None else None
    if not m:
        return default
    n = float(m.group(1))
    return default if n != n else min(hi, max(lo, n))  # NaN check


def numbers(v) -> list[float]:
    return [min(MAX_NUM, max(-MAX_NUM, float(x))) for x in NUM_RE.findall(v or "")]


def safe_path(base_dir: str, rel: str, allow_outside: bool = False) -> Path:
    """Resolve rel against base_dir; refuse anything that escapes base_dir unless allowed."""
    base = Path(base_dir).resolve()
    p = (base / rel).resolve()
    if not allow_outside and not p.is_relative_to(base):
        raise UnsafePathError(f"path {rel!r} is outside {str(base)!r} (use --allow-outside)")
    return p
