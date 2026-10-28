"""TOML colour themes -> CSS (variables + base rules). See docs/THEMES.md."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

BUNDLED = Path(__file__).parent / "themes"
HUES = ("red", "orange", "yellow", "green", "cyan", "blue", "purple")
ROLE_DEFAULTS = {
    "accent": "blue", "danger": "red", "node-fill": "surface", "node-stroke": "border",
    "node-text": "fg", "group-fill": "bg-alt", "group-stroke": "border", "group-text": "muted",
    "edge": "muted", "edge-text": "fg",
}
REQUIRED = ("bg", "surface", "fg", "muted", "border") + HUES


class ThemeError(ValueError):
    pass


def _mix(a: str, b: str, t: float) -> str:
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * t + y * (1 - t)):02x}" for x, y in zip(ca, cb))


def find_theme(name: str, base_dir: str = ".") -> Path:
    cand = Path(base_dir) / name
    if name.endswith(".toml") and cand.exists():
        return cand
    dirs = [d for d in os.environ.get("NODAL_THEME_PATH", "").split(os.pathsep) if d] + [str(BUNDLED)]
    for d in dirs:
        p = Path(d) / f"{name}.toml"
        if p.exists():
            return p
    raise ThemeError(f"unknown theme {name!r} (available: {', '.join(list_themes())})")


def list_themes() -> list[str]:
    return sorted(p.stem for p in BUNDLED.glob("*.toml"))


def load_theme(name: str, base_dir: str = ".", _seen=()) -> dict:
    path = find_theme(name, base_dir)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if data.get("schema", 1) != 1:
        raise ThemeError(f"{path}: unsupported schema {data['schema']}")
    if "extends" in data:
        if data["extends"] in _seen:
            raise ThemeError(f"{path}: extends cycle")
        parent = load_theme(data["extends"], str(path.parent), _seen + (name,))
        for sect in ("palette", "roles", "shape"):
            parent.setdefault(sect, {}).update(data.get(sect, {}))
        parent["name"] = data.get("name", name)
        parent["dark"] = data.get("dark", parent.get("dark", False))
        data = parent
    return data


def theme_css(name: str, base_dir: str = ".") -> str:
    t = load_theme(name, base_dir)
    pal = dict(t.get("palette", {}))
    missing = [k for k in REQUIRED if k not in pal]
    if missing:
        raise ThemeError(f"theme {name!r} palette missing: {', '.join(missing)}")
    for k, v in pal.items():
        if not (isinstance(v, str) and v.startswith("#") and len(v) == 7):
            raise ThemeError(f"theme {name!r}: palette.{k} must be #rrggbb, got {v!r}")
    pal.setdefault("bg-alt", _mix(pal["surface"], pal["bg"], 0.45))
    for h in HUES:
        pal.setdefault(f"{h}-soft", _mix(pal[h], pal["bg"], 0.22))
    roles = {**ROLE_DEFAULTS, **t.get("roles", {})}
    unknown = set(t.get("roles", {})) - set(ROLE_DEFAULTS)
    if unknown:
        raise ThemeError(f"theme {name!r}: unknown roles {sorted(unknown)}")
    shape = t.get("shape", {})

    def ref(v):
        return f"var(--{v})" if v in pal else v

    lines = [":root {"]
    lines += [f"  --{k}: {v};" for k, v in pal.items()]
    lines += [f"  --{k}: {ref(v)};" for k, v in roles.items()]
    lines.append("}")
    font = shape.get("font", "DejaVu Sans")
    radius = shape.get("radius", 6)
    lines.append(f'graph {{ background: var(--bg); color: var(--fg); font-family: "{font}", sans-serif; }}')
    lines.append(f"node {{ fill: var(--node-fill); stroke: var(--node-stroke); color: var(--node-text); "
                 f"border-radius: {radius}px; }}")
    lines.append("group { fill: var(--group-fill); stroke: var(--group-stroke); color: var(--group-text); }")
    lines.append("edge { stroke: var(--edge); color: var(--edge-text); }")
    # semantic helper classes usable on any node/group/edge: .red .green .accent ...
    for h in HUES + ("accent", "danger"):
        base = f"var(--{h})"
        soft = f"var(--{h}-soft)" if h in HUES else f"var(--{roles[h]}-soft)" if roles[h] in HUES else "var(--surface)"
        lines.append(f"node.{h}, group.{h} {{ fill: {soft}; stroke: {base}; }}")
        lines.append(f"edge.{h} {{ stroke: {base}; color: {base}; }}")
    lines.append("node.solid { fill: var(--fg); stroke: var(--fg); color: var(--bg); }")
    if "edge-width" in shape:
        lines.append(f"edge {{ stroke-width: {shape['edge-width']}; }}")
    return "\n".join(lines) + "\n"
