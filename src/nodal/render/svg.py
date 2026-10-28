"""SVG writer: Scene IR -> SVG text.

t=None  animated SVG: static values are the first keyframe, SMIL <animate> drives tracks.
t=float frozen frame at that time (used for --static/--at and APNG frames).
"""
from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from ..ir import Elem, Scene

SHADOW = ('<filter id="nodal-shadow" x="-20%" y="-20%" width="140%" height="150%">'
          '<feDropShadow dx="0" dy="2" stdDeviation="2.5" flood-opacity="0.18"/></filter>')


def num(v) -> str:
    if isinstance(v, float):
        s = f"{v:.2f}".rstrip("0").rstrip(".")
        return s if s not in ("", "-0") else "0"
    return str(v)


def path_d(segs) -> str:
    out = []
    for s in segs:
        out.append(s[0] + (" " + " ".join(num(float(x)) for x in s[1:]) if len(s) > 1 else ""))
    return " ".join(out)


class SvgWriter:
    def __init__(self, scene: Scene, t: float | None = None):
        self.scene, self.t = scene, t

    # ------------------------------------------------------------ attrs
    def paint_attrs(self, el: Elem) -> dict[str, str]:
        a = {}
        for k, v in el.paint.items():
            if k == "filter":
                a["filter"] = f"url(#nodal-{v})"
            else:
                a[k] = num(v)
        for tr in el.tracks:
            v = tr.values[0] if self.t is None else tr.at(self.t)
            a[tr.attr] = num(float(v))
        return a

    def smil(self, el: Elem) -> str:
        if self.t is not None:
            return ""
        return "".join(f'<animate attributeName="{tr.attr}" values="{";".join(num(float(v)) for v in tr.values)}" '
                       f'dur="{num(float(tr.dur))}s" repeatCount="indefinite"/>' for tr in el.tracks)

    @staticmethod
    def attrs_str(a: dict) -> str:
        return " ".join(f"{k}={quoteattr(str(v))}" for k, v in a.items())

    # ------------------------------------------------------------ elements
    def elem(self, el: Elem) -> str:
        g = el.geom
        base = {}
        if el.id:
            base["id"] = el.id
        if el.cls:
            base["class"] = el.cls
        if el.kind == "group":
            inner = "\n".join(self.elem(c) for c in el.children)
            return f"<g {self.attrs_str(base)}>\n{inner}\n</g>" if base else f"<g>\n{inner}\n</g>"
        if el.kind == "text":
            a = {"x": num(float(g["x"])), "y": num(float(g["y"])), "text-anchor": g.get("anchor", "middle")}
            a.update(self.paint_attrs(el))
            a.update(base)
            return f"<text {self.attrs_str(a)}>{escape(g['text'])}</text>"
        if el.kind == "rect":
            a = {"x": g["x"], "y": g["y"], "width": g["w"], "height": g["h"]}
            if g.get("rx"):
                a["rx"] = g["rx"]
        elif el.kind == "ellipse":
            a = {"cx": g["cx"], "cy": g["cy"], "rx": g["rx"], "ry": g["ry"]}
        elif el.kind == "circle":
            a = {"cx": g["cx"], "cy": g["cy"], "r": g["r"]}
        elif el.kind in ("polygon", "polyline"):
            a = {"points": " ".join(f"{num(float(x))},{num(float(y))}" for x, y in g["points"])}
        elif el.kind == "line":
            a = {k: g[k] for k in ("x1", "y1", "x2", "y2")}
        elif el.kind == "path":
            a = {"d": path_d(g["segs"])}
        elif el.kind == "image":
            a = {"x": g["x"], "y": g["y"], "width": g["w"], "height": g["h"], "href": g["href"],
                 "xlink:href": g["href"], "preserveAspectRatio": "xMidYMid meet"}
        else:
            return ""
        a = {k: num(float(v)) if isinstance(v, (int, float)) else v for k, v in a.items()}
        a.update(self.paint_attrs(el))
        a.update(base)
        kids = self.smil(el)
        tag = "path" if el.kind == "path" else el.kind
        return f"<{tag} {self.attrs_str(a)}>{kids}</{tag}>" if kids else f"<{tag} {self.attrs_str(a)}/>"

    # ------------------------------------------------------------ document
    def write(self) -> str:
        s = self.scene
        body = [self.elem(layer) for layer in s.layers]
        defs = []
        if "shadow" in s.effects():
            defs.append(SHADOW)
        head = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'width="{s.width:.0f}" height="{s.height:.0f}" viewBox="0 0 {num(s.width)} {num(s.height)}" '
                f'class="nodal">']
        if defs:
            head.append("<defs>" + "".join(defs) + "</defs>")
        if s.background:
            head.append(f'<rect x="0" y="0" width="{num(s.width)}" height="{num(s.height)}" fill="{s.background}"/>')
        return "\n".join(head + body + ["</svg>"]) + "\n"


def write_svg(scene: Scene, t: float | None = None) -> str:
    return SvgWriter(scene, t).write()
