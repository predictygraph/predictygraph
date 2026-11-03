# SPDX-FileCopyrightText: 2026 Reza Jelveh
#
# SPDX-License-Identifier: Apache-2.0

"""Line-oriented parser for the Predictygraph DSL (see docs/SPEC.md)."""
from __future__ import annotations

import re
from pathlib import Path

from .model import Bracket, Document, Edge, Group, Node
from .safe import MAX_EDGES, safe_path

MAX_ANNOTATIONS = 64  # legend entries / brackets per diagram
MAX_USE_DEPTH = 16  # nested `use` expansions
VAR_RE = re.compile(r"\$(?:\{([A-Za-z_]\w*)\}|([A-Za-z_]\w*))")
LET_RE = re.compile(r"^let\s+([A-Za-z_]\w*)\s*=\s*(.+)$")
DEF_RE = re.compile(r"^def\s+([A-Za-z_][\w-]*)\b(.*)\{\s*$")
BARE_RE = re.compile(r'^[^\s"{};,]+$')


class PdgSyntaxError(ValueError):
    def __init__(self, msg: str, line: int):
        super().__init__(f"line {line}: {msg}")
        self.line = line


TOKEN_RE = re.compile(
    r"""
    (?P<ws>[ \t]+)
  | (?P<string>"(?:[^"\\]|\\.)*")
  | (?P<arrow><?[-=.]{1,64}>|<[-=.]{1,64}|[-=.]{2,64})
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
            raise PdgSyntaxError(f"unexpected {text[pos:pos + 12]!r}", lineno)
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
    def __init__(self, base_dir: str = ".", allow_outside: bool = False):
        self.root = Group(id="__root__", kind="graph")
        self.doc = Document(root=self.root, base_dir=base_dir, allow_outside=allow_outside)
        self.stack = [self.root]
        self.vars: list[dict[str, str]] = [{}]  # one scope per open group
        self.defs: dict[str, tuple[dict[str, str | None], list[tuple[int, str]]]] = {}
        self.prefixes: list[str] = []  # `use` copies being expanded

    def q(self, item_id: str) -> str:
        """Qualify an ID written inside a `use` copy: `cpu` in copy `node1` is `node1-cpu`."""
        return "-".join(self.prefixes + [item_id])

    def _var(self, name: str, lineno: int) -> str:
        for scope in reversed(self.vars):
            if name in scope:
                return scope[name]
        raise PdgSyntaxError(f"unknown variable ${name}", lineno)

    def subst(self, line: str, lineno: int) -> str:
        """Replace `$NAME` / `${NAME}` (quoted outside strings when the value needs it)."""
        if "$" not in line:
            return line
        parts = re.split(r'("(?:[^"\\]|\\.)*")', line)
        for k, part in enumerate(parts):
            if k % 2:  # inside a string: plain text, escaped
                parts[k] = VAR_RE.sub(lambda m: self._var(m[1] or m[2], lineno)
                                      .replace("\\", "\\\\").replace('"', '\\"'), part)
            else:
                def bare(m):  # after `=` or `.` keep simple values bare; elsewhere it's a label
                    v = self._var(m[1] or m[2], lineno)
                    if m.start() and part[m.start() - 1] in "=." and BARE_RE.match(v):
                        return v
                    return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
                parts[k] = VAR_RE.sub(bare, part)
        return "".join(parts)

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
                raise PdgSyntaxError(f"unexpected token {val!r}", lineno)
        return label, classes, attrs

    def _annotation_room(self, stmt: str, existing: list, what: str, lineno: int) -> None:
        """`legend` / `bracket`: top level only, at most MAX_ANNOTATIONS of each."""
        if self.scope is not self.root:
            raise PdgSyntaxError(f"'{stmt}' only allowed at top level", lineno)
        if len(existing) >= MAX_ANNOTATIONS:
            raise PdgSyntaxError(f"too many {what} (limit {MAX_ANNOTATIONS})", lineno)

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
            raise PdgSyntaxError(f"duplicate id {item_id!r}", lineno)
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
                raise PdgSyntaxError("unbalanced '}'", lineno)
            self.stack.pop()
            self.vars.pop()
            return
        if "arrow" in kinds:
            return self.edge(toks, lineno)
        if toks[0][0] != "ident":
            raise PdgSyntaxError(f"statement cannot start with {head!r}", lineno)
        if head == "graph" and (len(toks) == 1 or toks[1][0] != "string"):
            if self.scope is not self.root:
                raise PdgSyntaxError("'graph' only allowed at top level", lineno)
            _, classes, attrs = self._tail(toks, 1, lineno)
            self.root.classes += classes
            self.root.attrs.update(attrs)
            return
        if head == "css" and len(toks) == 2 and toks[1][0] == "string":
            path = safe_path(self.doc.base_dir, unquote(toks[1][1]), self.doc.allow_outside)
            self.doc.stylesheets.append((path.read_text(encoding="utf-8"), str(path.parent)))
            return
        if head == "default" and len(toks) >= 2 and toks[1][1] in ("node", "edge", "group"):
            _, classes, attrs = self._tail(toks, 2, lineno)
            d = self.scope.defaults.setdefault(toks[1][1], {})
            d.update(attrs)
            if classes:
                d["__classes__"] = " ".join(classes)
            return
        if head == "use" and len(toks) >= 3 and toks[1][0] == "ident" and toks[2][0] == "ident":
            return self.use(toks, lineno)
        if head == "bracket" and len(toks) >= 2 and toks[1][0] == "ident":
            self._annotation_room(head, self.doc.brackets, "brackets", lineno)
            ids, i = [], 1
            while i < len(toks) and toks[i][0] in ("ident", "punct") and toks[i][1] != "{":
                if toks[i][0] == "ident":
                    ids.append(self.q(toks[i][1]))
                i += 1
            label, classes, attrs = self._tail(toks, i, lineno)
            self.doc.brackets.append(Bracket(ids=ids, label=label or "", classes=list(classes), attrs=attrs))
            return
        if head == "legend" and (len(toks) == 1 or toks[1][0] in ("string", "cls")):
            label, classes, attrs = self._tail(toks, 1, lineno)
            if not classes:  # `legend "Key"` names the box
                self._annotation_room(head, [], "", lineno)
                self.doc.legend_title = label
                return
            self._annotation_room(head, self.doc.legend, "legend entries", lineno)
            entry = Node(id=f"pdg-legend-{len(self.doc.legend)}", label=label or " ".join(classes),
                         classes=list(classes), attrs=attrs, parent=self.root)
            self.doc.legend.append(entry)
            return
        if head == "group" and len(toks) >= 2 and toks[1][0] == "ident":
            if toks[-1] != ("punct", "{"):
                raise PdgSyntaxError("group needs '{'", lineno)
            g = self._declare(self.q(toks[1][1]), lineno, cls=Group)
            g.label, g.classes, g.attrs = self._tail(toks[:-1], 2, lineno)
            self._apply_defaults(g, "group")
            self.stack.append(g)
            self.vars.append({})
            return
        # node declaration
        n = self._declare(self.q(head), lineno)
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
                groups[-1].append(self.q(val))
            elif kind == "punct" and val == ",":
                pass
            elif kind == "arrow":
                if not groups[-1]:
                    raise PdgSyntaxError("arrow without source", lineno)
                arrows.append(parse_arrow(val))
                groups.append([])
            else:
                break
            i += 1
        if not groups[-1]:
            raise PdgSyntaxError("arrow without target", lineno)
        label, classes, attrs = self._tail(toks, i, lineno)
        defaults: dict[str, str] = {}
        for g in reversed([self.scope] + self.scope.ancestors()):
            defaults.update(g.defaults.get("edge", {}))
        dcls = defaults.pop("__classes__", "").split()
        for a in groups:
            for nid in a:
                self._get_node(nid, lineno)
        count = sum(len(s) * len(d) for s, d in zip(groups, groups[1:]))
        if len(self.doc.edges) + count > MAX_EDGES:
            raise PdgSyntaxError(f"too many edges (limit {MAX_EDGES})", lineno)
        for (srcs, dsts), (arrow, body) in zip(zip(groups, groups[1:]), arrows):
            for s in srcs:
                for d in dsts:
                    e = Edge(src=s, dst=d, arrow=arrow, body=body, label=label,
                             classes=dcls + list(classes), attrs={**defaults, **attrs},
                             scope=self.scope, index=len(self.doc.edges))
                    e.id = f"e{e.index}"
                    self.doc.edges.append(e)

    def use(self, toks, lineno):
        """`use NAME ID ["Label"] [.class...] [param=value...] [attrs]`: one copy of a `def` block."""
        name, gid = toks[1][1], toks[2][1]
        if name not in self.defs:
            raise PdgSyntaxError(f"unknown block {name!r}", lineno)
        if len(self.prefixes) >= MAX_USE_DEPTH or name in getattr(self, "_expanding", []):
            raise PdgSyntaxError(f"block {name!r} uses itself", lineno)
        params, body = self.defs[name]
        label, classes, attrs = self._tail(toks, 3, lineno)
        args = {k: attrs.pop(k) for k in list(attrs) if k in params}
        missing = [k for k, v in params.items() if v is None and k not in args]
        if missing:
            raise PdgSyntaxError(f"use {name}: missing {missing[0]}=", lineno)
        g = self._declare(self.q(gid), lineno, cls=Group)
        g.label, g.classes, g.attrs = label, classes, attrs
        self._apply_defaults(g, "group")
        depth = len(self.stack)
        self.stack.append(g)
        self.vars.append({**{k: v for k, v in params.items() if v is not None}, **args,
                          "ID": gid, "LABEL": label if label is not None else gid})
        self.prefixes.append(gid)
        self._expanding = getattr(self, "_expanding", []) + [name]
        try:
            self.run(body)
        finally:
            self._expanding.pop()
            self.prefixes.pop()
        if len(self.stack) != depth + 1:
            raise PdgSyntaxError(f"unbalanced braces in block {name!r}", lineno)
        self.stack.pop()
        self.vars.pop()

    def define(self, name, head, lines, i, lineno):
        """Capture a `def NAME [params] {` block's raw lines up to its closing brace."""
        params: dict[str, str | None] = {}
        for kind, val in tokenize(head.strip(), lineno):
            if kind == "attr":
                k, v = val.split("=", 1)
                params[k] = unquote(v)
            elif kind == "ident":
                params[val] = None
            else:
                raise PdgSyntaxError(f"bad def parameter {val!r}", lineno)
        body, depth = [], 1
        while True:
            i += 1
            if i >= len(lines):
                raise PdgSyntaxError(f"unclosed def {name!r}", lineno)
            ln, text = lines[i]
            s = strip_comment(text).strip()
            depth += sum(1 if t == ("punct", "{") else -1 if t == ("punct", "}") else 0
                         for t in (tokenize(s, ln) if s and not s.startswith("css") else []))
            if s.startswith("css") and "{" in s:
                depth += s.count("{") - s.count("}")
            if depth <= 0:
                break
            body.append((ln, text))
        self.defs[name] = (params, body)
        return i

    # -- driver ----------------------------------------------------------
    def parse(self, text: str) -> Document:
        self.run(list(enumerate(text.splitlines(), 1)))
        return self.finish(len(text.splitlines()))

    def run(self, lines: list[tuple[int, str]]) -> None:
        i = 0
        while i < len(lines):
            lineno, line = lines[i]
            raw = strip_comment(line)
            stripped = raw.strip()
            m = LET_RE.match(stripped)
            if m:
                v = self.subst(m[2].strip(), lineno)
                if not (BARE_RE.match(v) or (len(v) > 1 and v[0] == v[-1] == '"')):
                    raise PdgSyntaxError(f"let {m[1]}: one value expected", lineno)
                self.vars[-1][m[1]] = unquote(v)
                i += 1
                continue
            m = DEF_RE.match(stripped)
            if m:
                i = self.define(m[1], m[2], lines, i, lineno) + 1
                continue
            m = re.match(r"^\s*css\s*\{(.*)$", line)
            if m:  # raw inline css block
                buf, depth, rest = [], 1, m.group(1)
                while True:
                    for j, ch in enumerate(rest):
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
                        raise PdgSyntaxError("unterminated css block", lineno)
                    rest = lines[i][1]
                self.doc.stylesheets.append(("".join(buf), self.doc.base_dir))
                tail = strip_comment(rest[j + 1:]).strip()
                if tail:  # statements after the closing brace on the same line
                    for stmt in split_statements(tokenize(self.subst(tail, lines[i][0]), lines[i][0])):
                        self.statement(stmt, lines[i][0])
                i += 1
                continue
            if stripped:
                for stmt in split_statements(tokenize(self.subst(stripped, lineno), lineno)):
                    self.statement(stmt, lineno)
            i += 1

    def finish(self, nlines: int) -> Document:
        if len(self.stack) != 1:
            raise PdgSyntaxError(f"unclosed group {self.stack[-1].id!r}", nlines)
        for e in self.doc.edges:
            for nid in (e.src, e.dst):
                if nid not in self.doc.items:
                    raise PdgSyntaxError(f"unknown id {nid!r}", 0)
        for b in self.doc.brackets:
            missing = [i for i in b.ids if i not in self.doc.items]
            if missing or not b.ids:
                raise PdgSyntaxError(f"bracket: unknown id {missing[0]!r}" if missing else "bracket needs ids", 0)
        return self.doc


def parse(text: str, base_dir: str = ".", allow_outside: bool = False) -> Document:
    return Parser(base_dir, allow_outside).parse(text)


def parse_file(path: str | Path, allow_outside: bool = False) -> Document:
    p = Path(path)
    return parse(p.read_text(encoding="utf-8"), str(p.parent), allow_outside)
