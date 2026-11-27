# SPDX-FileCopyrightText: 2026 Reza Jelveh
#
# SPDX-License-Identifier: Apache-2.0

"""TOML colour themes -> CSS (variables + base rules). See docs/THEMES.md."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

BUNDLED = Path(__file__).parent / "themes"
HUES = ("red", "orange", "yellow", "green", "cyan", "blue", "purple")
ROLE_DEFAULTS = {
    "accent": "blue",
    "danger": "red",
    "node-fill": "surface",
    "node-stroke": "border",
    "node-text": "fg",
    "group-fill": "bg-alt",
    "group-stroke": "border",
    "group-text": "muted",
    "edge": "muted",
    "edge-text": "fg",
}
REQUIRED = ("bg", "surface", "fg", "muted", "border") + HUES


class ThemeError(ValueError):
    pass


def _mix(a: str, b: str, t: float) -> str:
    ca = [int(a[i : i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * t + y * (1 - t)):02x}" for x, y in zip(ca, cb))


def _resolve_aliases(pal: dict, name: str) -> dict:
    """Palette values are #rrggbb or the name of another palette entry (`edge = "ink"`)."""
    out = {}
    for k, v in pal.items():
        seen = {k}
        while isinstance(v, str) and v in pal and v not in seen:
            seen.add(v)
            v = pal[v]
        if not (isinstance(v, str) and v.startswith("#") and len(v) == 7):
            raise ThemeError(f"theme {name!r}: palette.{k} must be #rrggbb or a palette name, got {pal[k]!r}")
        out[k] = v
    return out


CLASS_KEYS = {"fill", "stroke", "color", "sub", "edge", "title-fill", "font-weight", "sub-weight"}
BOX_KEYS = ("fill", "stroke", "color", "title-fill", "font-weight")


def _class_rules(classes: dict, pal: dict, name: str) -> list[str]:
    """`[classes] lime = { fill = "lime", color = "ink", sub = "ink-2", edge = "lime" }`:
    `node.lime, group.lime` get fill/stroke/color/font-weight (stroke defaults to fill),
    `node.lime sub` the `sub` colour and `sub-weight`, `edge.lime` the `edge` colour
    (default: the fill). Colours are palette names or any CSS colour; weights are CSS
    font weights (`400`, `bold`)."""
    lines = []
    for cls, spec in classes.items():
        if not isinstance(spec, dict) or set(spec) - CLASS_KEYS:
            raise ThemeError(f"theme {name!r}: classes.{cls} keys must be among {sorted(CLASS_KEYS)}")
        val = {k: f"var(--{v})" if isinstance(v, str) and v in pal else str(v) for k, v in spec.items()}
        box = {k: val[k] for k in BOX_KEYS if k in val}
        if "fill" in box:
            box.setdefault("stroke", box["fill"])
        if box:
            lines.append(f"node.{cls}, group.{cls} {{ " + " ".join(f"{k}: {v};" for k, v in box.items()) + " }")
        sub = {k: val[s] for k, s in (("color", "sub"), ("font-weight", "sub-weight")) if s in val}
        if sub:
            lines.append(f"node.{cls} sub {{ " + " ".join(f"{k}: {v};" for k, v in sub.items()) + " }")
        if "edge" in val or "fill" in val:
            c = val.get("edge", val.get("fill"))
            lines.append(f"edge.{cls} {{ stroke: {c}; color: {c}; }}")
    return lines


WEIGHTS = {"regular": 400, "bold": 700, "heavy": 900}

# Generic classes every theme gets, written against the required palette names so they
# fit light and dark themes alike. A theme's [classes] and css come later and may restyle them.
GENERIC = (
    ("label", "fill: none; stroke: none; font-weight: 400;"),  # text without a box
    ("plain", "font-weight: 400; color: var(--fg);"),
    ("strong", "font-weight: 700; color: var(--fg);"),
    ("quiet", "font-weight: 400; color: var(--muted);"),  # secondary text
    ("chip", "fill: var(--surface); stroke: none; font-weight: 400; color: var(--fg);"),
    ("card", "fill: var(--bg); stroke: var(--border);"),  # page-coloured box, hairline
    ("frame", "fill: var(--bg); stroke: var(--fg);"),  # page-coloured box, strong outline
    ("outline", "fill: none;"),  # outline only; colour it with .stroke-<name>
    ("placeholder", "fill: var(--surface); stroke: var(--border);"),  # free slot, unused capacity
    ("ghost", "fill: var(--bg); stroke: var(--muted); stroke-width: 1.2; stroke-dasharray: 4 3; color: var(--muted); font-weight: 400;"),
    ("band", "fill: var(--surface); stroke: none;"),  # filled strip without an outline
    ("open", "fill: none; stroke: none;"),  # group without a box (keeps its padding, unlike .bare)
)


BOXES = ("chip", "card", "frame", "placeholder", "band")  # page-like boxes: subtitles in muted


def _luminance(hex_: str) -> float:
    def ch(i):
        c = int(hex_[i : i + 2], 16) / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * ch(1) + 0.7152 * ch(3) + 0.0722 * ch(5)


def _contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def on_colour(pal: dict, name: str) -> str:
    """Text colour for a box filled with `name`: palette `on-<name>` if the theme sets it,
    else whichever of fg and bg contrasts more with the fill (bg on a tie)."""
    if f"on-{name}" in pal:
        return f"on-{name}"
    return "fg" if _contrast(pal[name], pal["fg"]) > _contrast(pal[name], pal["bg"]) else "bg"


def generic_rules(pal: dict) -> list[str]:
    """`.label .plain .strong .quiet .chip .card .frame .outline .placeholder .ghost .band
    .open` and `.on-<name>` (filled with a palette colour, readable text) for every entry."""
    out = [f"node.{c}, group.{c} {{ {decl} }}" for c, decl in GENERIC]
    out.append(", ".join(f"node.{c} sub" for c in BOXES) + " { color: var(--muted); }")
    for k in pal:
        if k.startswith("on-"):
            continue
        t = on_colour(pal, k)
        out.append(f"node.on-{k}, group.on-{k} {{ fill: var(--{k}); stroke: var(--{k}); color: var(--{t}); }}")
        out.append(f"node.on-{k} sub, group.on-{k} sub {{ color: var(--{t}); }}")
    return out


def utility_rules(pal: dict) -> list[str]:
    """`utilities = true`: one class per palette colour and property, so a diagram picks
    colours by name instead of writing CSS: `.fill-lime .stroke-ink .text-muted .sub-muted`
    (subtitle colour), plus
    `.fill-none .stroke-none` and the weights `.regular .bold .heavy`. They come after
    `[classes]` and the theme's `css`, so `.lime .text-ink` is lime with ink text."""
    sel = lambda c: f"node.{c}, group.{c}, edge.{c}"  # noqa: E731
    out = [f"{sel('fill-none')} {{ fill: none; }}", f"{sel('stroke-none')} {{ stroke: none; }}"]
    pal = {k: v for k, v in pal.items() if not k.startswith("on-")}
    for k in pal:
        out.append(f"node.fill-{k}, group.fill-{k} {{ fill: var(--{k}); }}")
        out.append(f"{sel('stroke-' + k)} {{ stroke: var(--{k}); }}")
    for k in pal:
        out.append(f"{sel('text-' + k)} {{ color: var(--{k}); }}")
        out.append(f"node.sub-{k} sub, group.sub-{k} sub {{ color: var(--{k}); }}")
    out += [f"{sel(w)} {{ font-weight: {v}; }}" for w, v in WEIGHTS.items()]
    return out


def find_theme(name: str, base_dir: str = ".") -> Path:
    cand = Path(base_dir) / name
    if name.endswith(".toml") and cand.exists():
        return cand
    dirs = [d for d in os.environ.get("PDG_THEME_PATH", "").split(os.pathsep) if d] + [str(BUNDLED)]
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
        for sect in ("palette", "roles", "shape", "seaborn", "classes"):  # [seaborn]: chart settings for decktile, unused here
            parent.setdefault(sect, {}).update(data.get(sect, {}))
        if "css" in data:  # extra rules stack: parent's first, then the child's
            parent["css"] = parent.get("css", "") + "\n" + data["css"]
        parent["name"] = data.get("name", name)
        parent["dark"] = data.get("dark", parent.get("dark", False))
        parent["utilities"] = data.get("utilities", parent.get("utilities", False))
        data = parent
    return data


def theme_css(name: str, base_dir: str = ".") -> str:
    t = load_theme(name, base_dir)
    pal = _resolve_aliases(dict(t.get("palette", {})), name)
    missing = [k for k in REQUIRED if k not in pal]
    if missing:
        raise ThemeError(f"theme {name!r} palette missing: {', '.join(missing)}")
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
    radius = shape.get("radius", 6)
    lines.append("graph { background: var(--bg); color: var(--fg); }")
    if "font" in shape:
        lines.append(f'graph {{ font-family: "{shape["font"]}", sans-serif; }}')
    lines.append(f"node {{ fill: var(--node-fill); stroke: var(--node-stroke); color: var(--node-text); border-radius: {radius}px; }}")
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
    lines += generic_rules(pal)
    lines += _class_rules(t.get("classes", {}), pal, name)
    if t.get("css"):  # free-form rules after the generated ones; var(--hue) works here
        lines.append(t["css"])
    if t.get("utilities"):  # last, so a utility class wins over the theme's own rules
        lines += utility_rules(pal)
    return "\n".join(lines) + "\n"
