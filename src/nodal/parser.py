"""Line-oriented parser for the Nodal DSL (see docs/SPEC.md)."""
from __future__ import annotations

import re
from pathlib import Path

from .model import Document, Edge, Group, Node


class NodalSyntaxError(ValueError):
    def __init__(self, msg: str, line: int):
        super().__init__(f"line {line}: {msg}")
        self.line = line


TOKEN_RE = re.compile(
    r"""
    (?P<ws>[ \t]+)
  | (?P<string>"(?:[^"\\]|\\.)*")
  | (?P<arrow><?[-=.]+>|<[-=.]+|[-=.]{2,})
  | (?P<attr>[A-Za-z_][\w-]*=(?:"(?:[^"\\]|\\.)*"|[^\s{}]+))
  | (?P<cls>\.[A-Za-z_][\w-]*)
  | (?P<ident>[A-Za-z_][\w-]*)
  | (?P<punct>[{},;])
    """,
    re.VERBOSE,
)

BODIES = {"-": "solid", "=": "thick", ".": "dashed"}


def unquote(s: str) -> str:
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
        return re.sub(r"\\(.)", lambda m: "\n" if m.group(1) == "n" else m.group(1), s)
    return s


def strip_comment(line: str) -> str:
    out, in_str, esc = [], False, False
    for i, ch in enumerate(line):
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
            out.append(ch)
        elif ch == "#" and (not out or out[-1] in " \t") and (i + 1 == len(line) or line[i + 1] in " \t#!"):
            break
        else:
            out.append(ch)
    return "".join(out)


def tokenize(text: str, lineno: int) -> list[tuple[str, str]]:
    pos, toks = 0, []
    while pos < len(text):
        m = TOKEN_RE.match(text, pos)
        if not m:
            raise NodalSyntaxError(f"unexpected {text[pos:pos + 12]!r}", lineno)
        kind = m.lastgroup
        if kind != "ws":
            toks.append((kind, m.group()))
        pos = m.end()
    return toks


def split_statements(toks):
    """Split on ';' and after '{' / around '}' so blocks may share a line."""
    cur = []
    for t in toks:
        if t == ("punct", ";"):
            if cur:
                yield cur
            cur = []
        elif t == ("punct", "{"):
            cur.append(t)
            yield cur
            cur = []
        elif t == ("punct", "}"):
            if cur:
                yield cur
            yield [t]
            cur = []
        else:
            cur.append(t)
    if cur:
        yield cur


def parse_arrow(tok: str) -> tuple[str, str]:
    start = tok.startswith("<")
    end = tok.endswith(">")
    body = tok.strip("<>")
    arrow = {(False, False): "none", (False, True): "end", (True, False): "start", (True, True): "both"}[(start, end)]
    return arrow, BODIES[body[0]]


class Parser:
    def __init__(self, base_dir: str = "."):
        self.root = Group(id="__root__", kind="graph")
        self.doc = Document(root=self.root, base_dir=base_dir)
        self.stack = [self.root]

    @property
    def scope(self) -> Group:
        return self.stack[-1]

    # -- helpers ---------------------------------------------------------
    def _tail(self, toks, i, lineno):
        label, classes, attrs = None, [], {}
        for kind, val in toks[i:]:
            if kind == "string" and label is None:
                label = unquote(val)
            elif kind == "cls":
                classes.append(val[1:])
            elif kind == "attr":
                k, v = val.split("=", 1)
                attrs[k] = unquote(v)
            elif kind == "punct" and val == "{":
                pass
            else:
                raise NodalSyntaxError(f"unexpected token {val!r}", lineno)
        return label, classes, attrs

    def _get_node(self, nid: str, lineno: int):
        item = self.doc.items.get(nid)
        if item is None:
            item = Node(id=nid, implicit=True, parent=self.scope)
            self.scope.children.append(item)
            self.doc.items[nid] = item
        return item

    def _declare(self, item_id, lineno, cls=Node):
        existing = self.doc.items.get(item_id)
        if existing is not None:
            if isinstance(existing, Node) and existing.implicit and cls is Node:
                existing.parent.children.remove(existing)
                existing.parent = self.scope
                self.scope.children.append(existing)
                existing.implicit = False
                return existing
            if cls is Node and isinstance(existing, Node):
                return existing  # re-declaration merges attributes
            raise NodalSyntaxError(f"duplicate id {item_id!r}", lineno)
        item = cls(id=item_id, parent=self.scope)
        self.scope.children.append(item)
        self.doc.items[item_id] = item
        return item

    # -- statements ------------------------------------------------------
    def statement(self, toks, lineno):
        kinds = [k for k, _ in toks]
        head = toks[0][1]
        if toks == [("punct", "}")]:
            if len(self.stack) == 1:
                raise NodalSyntaxError("unbalanced '}'", lineno)
            self.stack.pop()
            return
        if "arrow" in kinds:
            return self.edge(toks, lineno)
        if toks[0][0] != "ident":
            raise NodalSyntaxError(f"statement cannot start with {head!r}", lineno)
        if head == "graph" and (len(toks) == 1 or toks[1][0] != "string"):
            if self.scope is not self.root:
                raise NodalSyntaxError("'graph' only allowed at top level", lineno)
            _, classes, attrs = self._tail(toks, 1, lineno)
            self.root.classes += classes
            self.root.attrs.update(attrs)
            return
        if head == "css" and len(toks) == 2 and toks[1][0] == "string":
            path = Path(self.doc.base_dir) / unquote(toks[1][1])
            self.doc.stylesheets.append((path.read_text(), str(path.parent)))
            return
        if head == "default" and len(toks) >= 2 and toks[1][1] in ("node", "edge", "group"):
            _, classes, attrs = self._tail(toks, 2, lineno)
            d = self.scope.defaults.setdefault(toks[1][1], {})
            d.update(attrs)
            if classes:
                d["__classes__"] = " ".join(classes)
            return
        if head == "group" and len(toks) >= 2 and toks[1][0] == "ident":
            if toks[-1] != ("punct", "{"):
                raise NodalSyntaxError("group needs '{'", lineno)
            g = self._declare(toks[1][1], lineno, cls=Group)
            g.label, g.classes, g.attrs = self._tail(toks[:-1], 2, lineno)
            self._apply_defaults(g, "group")
            self.stack.append(g)
            return
        # node declaration
        n = self._declare(head, lineno)
        label, classes, attrs = self._tail(toks, 1, lineno)
        if label is not None:
            n.label = label
        n.classes += classes
        n.attrs.update(attrs)
        self._apply_defaults(n, "node")

    def _apply_defaults(self, item, kind):
        merged: dict[str, str] = {}
        for g in reversed([self.scope] + self.scope.ancestors()):
            merged.update(g.defaults.get(kind, {}))
        extra = merged.pop("__classes__", "")
        item.classes = extra.split() + [c for c in item.classes if c not in extra.split()]
        item.attrs = {**merged, **item.attrs}

    def edge(self, toks, lineno):
        groups: list[list[str]] = [[]]
        arrows: list[tuple[str, str]] = []
        i = 0
        while i < len(toks):
            kind, val = toks[i]
            if kind == "ident":
                groups[-1].append(val)
            elif kind == "punct" and val == ",":
                pass
            elif kind == "arrow":
                if not groups[-1]:
                    raise NodalSyntaxError("arrow without source", lineno)
                arrows.append(parse_arrow(val))
                groups.append([])
            else:
                break
            i += 1
        if not groups[-1]:
            raise NodalSyntaxError("arrow without target", lineno)
        label, classes, attrs = self._tail(toks, i, lineno)
        defaults: dict[str, str] = {}
        for g in reversed([self.scope] + self.scope.ancestors()):
            defaults.update(g.defaults.get("edge", {}))
        dcls = defaults.pop("__classes__", "").split()
        for a in groups:
            for nid in a:
                self._get_node(nid, lineno)
        for (srcs, dsts), (arrow, body) in zip(zip(groups, groups[1:]), arrows):
            for s in srcs:
                for d in dsts:
                    e = Edge(src=s, dst=d, arrow=arrow, body=body, label=label,
                             classes=dcls + list(classes), attrs={**defaults, **attrs},
                             scope=self.scope, index=len(self.doc.edges))
                    e.id = f"e{e.index}"
                    self.doc.edges.append(e)

    # -- driver ----------------------------------------------------------
    def parse(self, text: str) -> Document:
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            lineno = i + 1
            raw = strip_comment(lines[i])
            stripped = raw.strip()
            m = re.match(r"^\s*css\s*\{(.*)$", lines[i])
            if m:  # raw inline css block
                buf, depth, rest = [], 1, m.group(1)
                while True:
                    for ch in rest:
                        if ch == "{":
                            depth += 1
                        elif ch == "}":
                            depth -= 1
                            if depth == 0:
                                break
                        buf.append(ch)
                    if depth == 0:
                        break
                    buf.append("\n")
                    i += 1
                    if i >= len(lines):
                        raise NodalSyntaxError("unterminated css block", lineno)
                    rest = lines[i]
                self.doc.stylesheets.append(("".join(buf), self.doc.base_dir))
                i += 1
                continue
            if stripped:
                for stmt in split_statements(tokenize(stripped, lineno)):
                    self.statement(stmt, lineno)
            i += 1
        if len(self.stack) != 1:
            raise NodalSyntaxError(f"unclosed group {self.stack[-1].id!r}", len(lines))
        for e in self.doc.edges:
            for nid in (e.src, e.dst):
                if nid not in self.doc.items:
                    raise NodalSyntaxError(f"unknown id {nid!r}", 0)
        return self.doc


def parse(text: str, base_dir: str = ".") -> Document:
    return Parser(base_dir).parse(text)


def parse_file(path: str | Path) -> Document:
    p = Path(path)
    return parse(p.read_text(encoding="utf-8"), str(p.parent))
