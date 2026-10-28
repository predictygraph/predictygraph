"""CSS subset resolution with tinycss2 (no browser)."""
from __future__ import annotations

import re
from dataclasses import dataclass

import tinycss2

from .model import Document, Edge, Group, Item
from .safe import MAX_VAR_LEN, number

BUILTIN = """
graph { font-family: "DejaVu Sans", sans-serif; font-size: 14px; color: #1f2937;
        fill: none; padding: 16px; }
node  { fill: #ffffff; stroke: #374151; stroke-width: 1.5; border-radius: 6px;
        padding: 8px 14px; color: #111827; min-width: 40px; min-height: 28px; }
group { fill: #f3f4f6; stroke: #9ca3af; stroke-width: 1; border-radius: 10px;
        padding: 14px; color: #374151; font-size: 12px; font-weight: bold;
        label-position: top; }
edge  { stroke: #4b5563; stroke-width: 1.5; color: #374151; font-size: 11px; }
"""

@dataclass
class Selector:
    parts: list[tuple[str | None, str | None, list[str]]]  # (type, id, classes), descendant chain

    @property
    def specificity(self):
        a = sum(1 for _, i, _ in self.parts if i)
        b = sum(len(c) for _, _, c in self.parts)
        c = sum(1 for t, _, _ in self.parts if t)
        return (a, b, c)


SIMPLE_RE = re.compile(r"([A-Za-z*][\w-]*)?((?:[#.][\w-]+)*)")


def parse_selector(text: str) -> Selector | None:
    parts = []
    for comp in text.split():
        m = SIMPLE_RE.fullmatch(comp)
        if not m:
            return None
        typ = m.group(1) if m.group(1) not in (None, "*") else None
        ident, classes = None, []
        for sigil, name in re.findall(r"([#.])([\w-]+)", m.group(2) or ""):
            if sigil == "#":
                ident = name
            else:
                classes.append(name)
        parts.append((typ, ident, classes))
    return Selector(parts) if parts else None


def match_simple(part, item) -> bool:
    typ, ident, classes = part
    if typ and typ != item.kind:
        return False
    if ident and ident != item.id:
        return False
    return all(c in item.classes for c in classes)


def matches(sel: Selector, item, ancestors: list) -> bool:
    if not match_simple(sel.parts[-1], item):
        return False
    rest = sel.parts[:-1]
    anc = list(ancestors)
    for part in reversed(rest):
        while anc and not match_simple(part, anc[0]):
            anc.pop(0)
        if not anc:
            return False
        anc.pop(0)
    return True


class StyleSheet:
    def __init__(self):
        self.rules: list[tuple[Selector, dict[str, str], int]] = []
        self.vars: dict[str, str] = {}
        self._order = 0

    def add(self, css: str):
        for rule in tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True):
            if rule.type != "qualified-rule":
                continue
            decls = {}
            for d in tinycss2.parse_declaration_list(rule.content, skip_comments=True, skip_whitespace=True):
                if d.type == "declaration":
                    decls[d.lower_name] = tinycss2.serialize(d.value).strip()
            prelude = tinycss2.serialize(rule.prelude).strip()
            for sel_text in prelude.split(","):
                sel_text = sel_text.strip()
                if sel_text in (":root", "html"):
                    self.vars.update({k: v for k, v in decls.items() if k.startswith("--")})
                    continue
                sel = parse_selector(sel_text)
                if sel:
                    self._order += 1
                    self.rules.append((sel, decls, self._order))

    def compute(self, item, ancestors) -> dict[str, str]:
        hits = [(sel.specificity, order, decls) for sel, decls, order in self.rules
                if matches(sel, item, ancestors)]
        out: dict[str, str] = {}
        for _, _, decls in sorted(hits, key=lambda h: (h[0], h[1])):
            out.update(decls)
        return out

    def resolve_vars(self, style: dict[str, str]) -> dict[str, str]:
        local = {**self.vars, **{k: v for k, v in style.items() if k.startswith("--")}}
        var_re = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,((?:[^()]|\([^()]*\))*))?\)")

        def sub(v, depth=0):
            if depth > 8 or "var(" not in v or len(v) > MAX_VAR_LEN:
                return v[:MAX_VAR_LEN]
            def rep(m):
                name, fb = m.group(1), m.group(2)
                return local.get(name, fb.strip() if fb else "")
            return sub(var_re.sub(rep, v), depth + 1)

        return {k: sub(v) for k, v in style.items()}


BOX_KEYS = ("fill", "stroke", "color", "font-size", "stroke-width", "border-radius", "font-weight",
            "stroke-dasharray", "padding", "border", "border-speed")
EDGE_KEYS = ("arrow", "head", "head-start", "head-size", "route", "radius", "stub", "flow", "flow-speed",
             "diagonal", "diagonal-angle")
INHERITED_EDGE_KEYS = tuple(k for k in EDGE_KEYS if k not in ("flow", "head-start"))


@dataclass
class _Label:
    """Pseudo item so `label` / `edge.x label` selectors match an edge's label."""
    classes: list
    id: str = ""
    kind: str = "label"


def apply_styles(doc: Document) -> None:
    sheet = StyleSheet()
    sheet.add(BUILTIN)
    for css, _ in doc.stylesheets:
        sheet.add(css)
    root = doc.root
    root.style = sheet.resolve_vars(sheet.compute(root, []))

    for item in doc.walk():
        anc = item.ancestors()  # nearest first; root last
        parent = item.parent.style if item.parent else root.style
        st = {k: parent[k] for k in ("font-family",) if k in parent}
        st.update(sheet.compute(item, anc))
        st.update({k: v for k, v in item.attrs.items() if k in BOX_KEYS})
        item.style = sheet.resolve_vars(st)
    ge = root.attrs
    for e in doc.edges:
        anc = [a for a in (([e.scope] + e.scope.ancestors()) if e.scope is not root else [root]) if a is not None]
        st = {"font-family": root.style.get("font-family", "sans-serif")}
        st.update(sheet.compute(e, anc))
        if "edge-width" in ge:
            st["stroke-width"] = ge["edge-width"]
        groups = [ge] + [g.attrs for g in reversed(anc) if g is not root]  # nearest group wins
        for k in INHERITED_EDGE_KEYS:
            for attrs in groups:
                if k in attrs:
                    st[k] = attrs[k]
        for k, v in e.attrs.items():
            if k == "width":
                st["stroke-width"] = v
            elif k in EDGE_KEYS or k in ("stroke", "color", "stroke-dasharray", "font-size"):
                st[k] = v
        e.style = sheet.resolve_vars(st)
        lab = sheet.compute(_Label(e.classes), [e] + anc)
        e.label_style = sheet.resolve_vars({**{k: e.style[k] for k in ("font-family", "font-size", "color")
                                               if k in e.style}, **lab})


def px(v: str | None, default: float = 0.0) -> float:
    return number(v, default)


def box4(v: str | None, default: float = 0.0) -> tuple[float, float, float, float]:
    """CSS shorthand -> (top, right, bottom, left)."""
    if not v:
        return (default,) * 4
    vals = [px(x) for x in v.split()]
    if len(vals) == 1:
        return (vals[0],) * 4
    if len(vals) == 2:
        return (vals[0], vals[1], vals[0], vals[1])
    if len(vals) == 3:
        return (vals[0], vals[1], vals[2], vals[1])
    return tuple(vals[:4])
