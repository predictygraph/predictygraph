# SPDX-FileCopyrightText: 2026 Reza Jelveh
#
# SPDX-License-Identifier: Apache-2.0

"""CSS subset resolution with tinycss2 (no browser)."""
from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass

import tinycss2

from .model import Document, Edge, Group, Item
from .safe import MAX_VAR_LEN, number

BUILTIN = (Path(__file__).parent / "default.css").read_text()

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
    def __init__(self, target: str | None = None):
        self.rules: list[tuple[Selector, dict[str, str], int]] = []
        self.vars: dict[str, str] = {}
        self._order = 0
        self.target = target

    def target_matches(self, prelude) -> bool:
        """`@target macos, windows { ... }` applies when the active target is listed."""
        names = {t.strip().lower() for t in tinycss2.serialize(prelude).split(",") if t.strip()}
        return self.target is not None and self.target in names

    def add(self, css: str):
        self.add_rules(tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True))

    def add_rules(self, rules):
        for rule in rules:
            if rule.type == "at-rule" and rule.lower_at_keyword == "target":
                if rule.content is not None and self.target_matches(rule.prelude):
                    self.add_rules(tinycss2.parse_rule_list(rule.content, skip_comments=True,
                                                            skip_whitespace=True))
                continue
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
            "stroke-dasharray", "padding", "border", "border-speed", "accent-bar", "accent-side", "title-fill")
EDGE_KEYS = ("arrow", "head", "head-start", "head-size", "route", "radius", "stub", "flow", "flow-speed",
             "diagonal", "diagonal-angle")
INHERITED_EDGE_KEYS = tuple(k for k in EDGE_KEYS if k not in ("flow", "head-start"))
TEXT_KEYS = ("font-family", "font-size", "color", "font-weight", "font-style", "text-align")


@dataclass
class _Part:
    """Pseudo item so `label`, `sub`, `step`, `caption`, `legend` selectors match a piece
    of text that belongs to an item (an edge label, a node subtitle, a step badge, ...)."""
    kind: str
    classes: list
    id: str = ""


def part_style(sheet: "StyleSheet", kind: str, owner, anc: list, inherit: dict) -> dict[str, str]:
    """Style for a text part: inherits text keys from its owner, then CSS for `kind`.
    Subtitles drop the owner's weight: a bold title should not make the second line bold.
    `em`/`%` font sizes are relative to the owner's size."""
    base = {k: inherit[k] for k in TEXT_KEYS if k in inherit and not (kind == "sub" and k == "font-weight")}
    st = sheet.resolve_vars({**base, **sheet.compute(_Part(kind, list(owner.classes)), [owner] + anc)})
    fs = st.get("font-size", "").strip()
    if fs.endswith("em"):
        st["font-size"] = f"{px(inherit.get('font-size'), 14) * number(fs[:-2], 1, 0.1, 10):.2f}px"
    elif fs.endswith("%"):
        st["font-size"] = f"{px(inherit.get('font-size'), 14) * number(fs[:-1], 100, 10, 1000) / 100:.2f}px"
    return st


def number_steps(doc: Document) -> None:
    """`graph steps=auto`: number every edge without its own `step=` in file order."""
    if doc.root.attrs.get("steps") != "auto":
        return
    n = 0
    for e in doc.edges:
        if "step" in e.attrs:
            continue
        n += 1
        e.attrs["step"] = str(n)


def apply_styles(doc: Document, target: str | None = None) -> None:
    sheet = StyleSheet(target)
    sheet.add(BUILTIN)
    for css, _ in doc.stylesheets:
        sheet.add(css)
    root = doc.root
    number_steps(doc)
    root.style = sheet.resolve_vars(sheet.compute(root, []))
    root.part_styles = {k: part_style(sheet, k, root, [], root.style) for k in ("caption", "legend")}
    for b in doc.brackets:
        b.style = sheet.resolve_vars({"font-family": root.style.get("font-family", "sans-serif"),
                                      **sheet.compute(b, [root])})

    for item in [*doc.walk(), *doc.legend]:
        anc = item.ancestors()  # nearest first; root last
        parent = item.parent.style if item.parent else root.style
        st = {k: parent[k] for k in ("font-family",) if k in parent}
        st.update(sheet.compute(item, anc))
        st.update({k: v for k, v in item.attrs.items() if k in BOX_KEYS})
        item.style = sheet.resolve_vars(st)
        if "sub" in item.attrs:
            item.sub_style = part_style(sheet, "sub", item, anc, item.style)
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
        e.label_style = part_style(sheet, "label", e, anc, e.style)
        if "step" in e.attrs:
            e.step_style = part_style(sheet, "step", e, anc, e.style)


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
