#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 The predictygraph Authors
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Convert the Graphviz DOT subset used in slide decks to predictygraph (.pdg).

Handles: digraph/graph, rankdir, node/edge defaults, nodes and edges with
attributes, edge chains, subgraph cluster_* -> group, { rank=same; a; b } ->
same rank (rank=N pinned from a topological order), label/class/shape/style/
colours/penwidth/constraint/arrowhead/dir. Ignored with a note: HTML labels,
ports, lhead/ltail, record shapes, layout tuning (ranksep, nodesep, splines...).

Usage: dot2pdg.py FILE.md [--write]   converts every ```dot block in a Markdown file
       dot2pdg.py FILE.dot            prints the .pdg
"""

import argparse
import re
import sys
from collections import defaultdict, deque
from pathlib import Path

SHAPES = {"box": "box", "rect": "box", "rectangle": "box", "square": "square",
          "ellipse": "ellipse", "oval": "ellipse", "circle": "circle", "doublecircle": "circle",
          "diamond": "diamond", "cylinder": "cylinder", "note": "note", "hexagon": "hexagon",
          "plaintext": "none", "plain": "none", "none": "none", "underline": "none",
          "Mrecord": "round", "record": "box", "component": "box", "folder": "note",
          "tab": "note", "box3d": "box", "parallelogram": "box", "point": "circle"}
IGNORED_GRAPH = {"bgcolor", "fontname", "fontsize", "fontcolor", "ranksep", "nodesep", "splines",
                 "compound", "newrank", "concentrate", "pad", "margin", "size", "ratio", "dpi",
                 "ordering", "outputorder", "nojustify", "labelloc", "labeljust", "center",
                 "penwidth", "style", "color", "fillcolor", "remincross", "searchsize"}


class Tok:
    RX = re.compile(r'''
        (?P<ws>\s+|//[^\n]*|/\*.*?\*/|\#[^\n]*)
      | (?P<str>"(?:\\.|[^"\\])*")
      | (?P<html><(?:[^<>]|<[^<>]*>)*>)
      | (?P<arrow>->|--)
      | (?P<punct>[{}\[\];,=:])
      | (?P<id>[A-Za-z_\x80-\uffff][\w.\x80-\uffff]*|-?(?:\d+\.?\d*|\.\d+))
    ''', re.S | re.X)

    def __init__(self, text: str):
        self.toks, pos = [], 0
        while pos < len(text):
            m = self.RX.match(text, pos)
            if not m:
                raise ValueError(f"cannot tokenise near: {text[pos:pos + 30]!r}")
            pos = m.end()
            kind = m.lastgroup
            if kind == "ws":
                continue
            v = m.group()
            if kind == "str":
                v = v[1:-1].replace('\\"', '"').replace("\\n", "\n").replace("\\l", "\n")
            elif kind == "html":
                v = re.sub(r"<br\s*/?>", "\n", v[1:-1], flags=re.I)
                v = re.sub(r"<[^>]+>", "", v).strip()
                kind = "str"
            self.toks.append((kind, v))
        self.i = 0

    def peek(self, k=0):
        return self.toks[self.i + k] if self.i + k < len(self.toks) else (None, None)

    def next(self):
        t = self.peek()
        self.i += 1
        return t

    def accept(self, v):
        if self.peek()[1] == v and self.peek()[0] in ("punct", "arrow"):
            self.i += 1
            return True
        return False


class Graph:
    def __init__(self):
        self.attrs: dict = {}
        self.node_defaults: dict = {}
        self.edge_defaults: dict = {}
        self.nodes: dict[str, dict] = {}       # id -> attrs (merged)
        self.node_group: dict[str, str] = {}   # id -> innermost group id
        self.groups: dict[str, dict] = {}      # id -> {"attrs", "parent", "children"}
        self.group_order: list[str] = []
        self.edges: list[tuple[str, str, dict]] = []
        self.same_rank: list[list[str]] = []
        self.order: list[str] = []
        self.notes: list[str] = []


class Parser:
    def __init__(self, text: str):
        self.t = Tok(text)
        self.g = Graph()
        self.anon = 0

    def parse(self) -> Graph:
        kind = self.t.next()[1]
        if kind == "strict":
            kind = self.t.next()[1]
        self.g.directed = kind == "digraph"
        if self.t.peek()[0] in ("id", "str"):
            self.t.next()
        self.block(None, dict(), dict())
        return self.g

    def attr_list(self) -> dict:
        out = {}
        while self.t.accept("["):
            while not self.t.accept("]"):
                k = self.t.next()[1]
                v = True
                if self.t.accept("="):
                    v = self.t.next()[1]
                out[k] = v
                self.t.accept(",") or self.t.accept(";")
        return out

    def node_id(self) -> str:
        nid = self.t.next()[1]
        if self.t.accept(":"):  # port
            self.t.next()
            if self.t.accept(":"):
                self.t.next()
        return nid

    def touch(self, nid, group, ndef):
        if nid not in self.g.nodes:
            self.g.nodes[nid] = dict(ndef)
            self.g.node_group[nid] = group
            self.g.order.append(nid)

    def block(self, group, ndef, edef):
        self.t.accept("{")
        while True:
            kind, v = self.t.peek()
            if v is None or (kind == "punct" and v == "}"):
                self.t.next()
                return
            if kind == "punct" and v in (";", ","):
                self.t.next()
                continue
            if v in ("node", "edge", "graph") and self.t.peek(1)[1] == "[":
                self.t.next()
                a = self.attr_list()
                if v == "node":
                    ndef = {**ndef, **a}
                elif v == "edge":
                    edef = {**edef, **a}
                else:
                    self.graph_attrs(group, a)
                continue
            if v == "subgraph" or (kind == "punct" and v == "{"):
                self.subgraph(group, ndef, edef)
                continue
            if self.t.peek(1)[1] == "=" and self.t.peek(1)[0] == "punct":
                k = self.t.next()[1]
                self.t.next()
                self.graph_attrs(group, {k: self.t.next()[1]})
                continue
            self.stmt(group, ndef, edef)

    def graph_attrs(self, group, a):
        target = self.g.attrs if group is None else self.g.groups[group]["attrs"]
        target.update(a)

    def subgraph(self, parent, ndef, edef):
        name = None
        if self.t.peek()[1] == "subgraph":
            self.t.next()
            if self.t.peek()[0] in ("id", "str"):
                name = self.t.next()[1]
        start = len(self.g.order)
        before = set(self.g.nodes)
        if name and name.startswith("cluster"):
            gid = re.sub(r"\W", "_", name[len("cluster"):].lstrip("_")) or f"g{len(self.g.groups)}"
            if gid in self.g.groups or gid in self.g.nodes:
                gid = f"{gid}_g"
            self.g.groups[gid] = {"attrs": {}, "parent": parent, "nodes": []}
            self.g.group_order.append(gid)
            self.block(gid, ndef, edef)
            return
        # plain subgraph or anonymous { }: same group, maybe rank=same
        mark = {"rank": None}
        sub_attrs = {}
        saved = self.g.attrs if parent is None else self.g.groups[parent]["attrs"]
        snapshot = dict(saved)
        self.block(parent, ndef, edef)
        rank = saved.get("rank")
        if rank != snapshot.get("rank"):
            if snapshot.get("rank") is None:
                saved.pop("rank", None)
            else:
                saved["rank"] = snapshot["rank"]
        members = [n for n in self.g.order[start:]] + \
                  [n for n in self._mentioned if n in before]
        self._mentioned = []
        if rank == "same" and len(members) > 1:
            self.g.same_rank.append(list(dict.fromkeys(members)))

    _mentioned: list = []

    def stmt(self, group, ndef, edef):
        ids = [self.node_id()]
        while self.t.peek()[0] == "arrow":
            self.t.next()
            if self.t.peek()[1] in ("{", "subgraph"):
                self.g.notes.append("edge to a subgraph flattened")
                start = len(self.g.order)
                self.subgraph(group, ndef, edef)
                ids.append(self.g.order[start] if len(self.g.order) > start else ids[-1])
            else:
                ids.append(self.node_id())
        a = self.attr_list()
        for nid in ids:
            fresh = nid not in self.g.nodes
            self.touch(nid, group, ndef)
            if not fresh:
                self._mentioned.append(nid)
        if len(ids) == 1:
            self.g.nodes[ids[0]].update(a)
            if group and self.g.node_group[ids[0]] != group and ids[0] in self.g.nodes:
                pass
        else:
            ea = {**edef, **a}
            for s, d in zip(ids, ids[1:]):
                self.g.edges.append((s, d, ea))


class Emitter:
    CLASS_RX = re.compile(r"^[A-Za-z_][\w-]*$")

    def __init__(self, g: Graph):
        self.g = g
        self.out: list[str] = []

    @staticmethod
    def q(s) -> str:
        s = str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{s}"'

    @staticmethod
    def ident(s: str) -> str:
        s = re.sub(r"[^\w-]", "_", s)
        return s if re.match(r"[A-Za-z_]", s) else f"n_{s}"

    def colour(self, v):
        v = str(v)
        if v in ("transparent", "none", "invis"):
            return "none"
        if v.startswith("#") and len(v) == 9:  # #RRGGBBAA -> keep rgb
            return v[:7]
        return v.split(":")[0]

    def node_attrs(self, a: dict, is_node=True) -> list[str]:
        out, classes = [], []
        style = str(a.get("style", ""))
        if a.get("class"):
            classes += [c for c in str(a["class"]).split() if self.CLASS_RX.match(c)]
        if is_node:
            shape = SHAPES.get(str(a.get("shape", "")), None)
            if "rounded" in style and shape in (None, "box"):
                shape = "round"
            if shape and shape != "box":
                out.append(f"shape={shape}")
            filled = "filled" in style or "fillcolor" in a
            if filled and a.get("fillcolor"):
                out.append(f"fill={self.colour(a['fillcolor'])}")
            elif filled and a.get("color") and not a.get("fillcolor"):
                out.append(f"fill={self.colour(a['color'])}")
            if a.get("color"):
                out.append(f"stroke={self.colour(a['color'])}")
            if a.get("fontcolor"):
                out.append(f"color={self.colour(a['fontcolor'])}")
            if "dashed" in style:
                out.append('stroke-dasharray="5 3"')
            elif "dotted" in style:
                out.append('stroke-dasharray="1.5 3"')
            if "invis" in style:
                out.append("opacity=0")
            if a.get("penwidth"):
                out.append(f"stroke-width={a['penwidth']}")
            if "bold" in style:
                out.append("stroke-width=2.5")
        return [f".{c}" for c in classes] + out

    def edge_attrs(self, a: dict) -> tuple[str, list[str]]:
        style = str(a.get("style", ""))
        body = "-"
        if "dashed" in style or "dotted" in style:
            body = "."
        elif "bold" in style:
            body = "="
        heads = (str(a.get("dir", "forward")) if self.g.directed else str(a.get("dir", "none")))
        arrow = {"forward": f"{body}{body}>" if body != "-" else "->",
                 "back": f"<{body}{body}" if body != "-" else "<-",
                 "both": f"<{body}{body}>" if body != "-" else "<->",
                 "none": f"{body}{body}" if body != "-" else "--"}.get(heads, "->")
        if str(a.get("arrowhead", "")) == "none" and heads == "forward":
            arrow = f"{body}{body}"
        out = []
        if a.get("color"):
            out.append(f"stroke={self.colour(a['color'])}")
        if a.get("fontcolor"):
            out.append(f"color={self.colour(a['fontcolor'])}")
        if a.get("penwidth"):
            out.append(f"width={a['penwidth']}")
        if str(a.get("constraint", "")).lower() == "false":
            out.append("constraint=false")
        if "invis" in style:
            out.append("opacity=0")
        if a.get("class"):
            out = [f".{c}" for c in str(a["class"]).split() if self.CLASS_RX.match(c)] + out
        return arrow, out

    def ranks(self) -> dict[str, int]:
        """Longest-path ranks from constraining edges, then rank=same groups snapped
        to their deepest member. Only needed when rank=same is used."""
        if not self.g.same_rank:
            return {}
        succ, indeg = defaultdict(list), defaultdict(int)
        nodes = list(self.g.order)
        for s, d, a in self.g.edges:
            if str(a.get("constraint", "")).lower() == "false" or s == d:
                continue
            if str(a.get("dir", "")) == "back":
                s, d = d, s
            succ[s].append(d)
            indeg[d] += 1
        rank = {n: 0 for n in nodes}
        q = deque(n for n in nodes if indeg[n] == 0)
        seen = 0
        while q:
            n = q.popleft()
            seen += 1
            for m in succ[n]:
                rank[m] = max(rank[m], rank[n] + 1)
                indeg[m] -= 1
                if indeg[m] == 0:
                    q.append(m)
        for _ in range(4):
            for grp in self.g.same_rank:
                r = max(rank.get(n, 0) for n in grp)
                for n in grp:
                    rank[n] = r
            for s, d, a in self.g.edges:
                if str(a.get("constraint", "")).lower() != "false" and rank.get(d, 0) <= rank.get(s, 0) and s != d:
                    if not any(s in grp and d in grp for grp in self.g.same_rank):
                        rank[d] = rank[s] + 1
        low = min(rank.values(), default=0)  # first rank is always 0
        return {n: r - low for n, r in rank.items()}

    def emit(self) -> str:
        g = self.g
        head = ["graph"]
        rd = str(g.attrs.get("rankdir", "TB")).upper()
        head.append(f"dir={rd}")
        if str(g.attrs.get("splines", "")) in ("ortho", "polyline"):
            head.append("route=ortho")
        self.out.append(" ".join(head))
        ranks = self.ranks()
        if ranks:
            self.out[0] += " order=source"
        ids = {n: self.ident(n) for n in g.order}
        taken = set(ids.values())
        gids = {}
        for gid in g.groups:
            name = self.ident(gid)
            while name in taken:
                name = f"{name}_group"
            taken.add(name)
            gids[gid] = name

        def node_line(n, indent):
            a = g.nodes[n]
            label = a.get("label", n)
            parts = [ids[n]]
            if label != n or not re.match(r"^[A-Za-z_][\w-]*$", n):
                parts.append(self.q(label))
            parts += self.node_attrs(a)
            if n in ranks and len(g.groups) == 0:
                parts.append(f"rank={ranks[n]}")
            return "  " * indent + " ".join(parts)

        def group_block(gid, indent):
            a = g.groups[gid]["attrs"]
            parts = ["group", gids[gid]]
            if a.get("label"):
                parts.append(self.q(a["label"]))
            style = str(a.get("style", ""))
            if a.get("class"):
                parts += [f".{c}" for c in str(a["class"]).split() if self.CLASS_RX.match(c)]
            if "filled" in style and (a.get("fillcolor") or a.get("color")):
                parts.append(f"fill={self.colour(a.get('fillcolor') or a.get('color'))}")
            if a.get("color") or a.get("pencolor"):
                parts.append(f"stroke={self.colour(a.get('pencolor') or a.get('color'))}")
            if "dashed" in style:
                parts.append('stroke-dasharray="5 3"')
            if "invis" in style:
                parts.append("stroke=none fill=none")
            if a.get("fontcolor"):
                parts.append(f"color={self.colour(a['fontcolor'])}")
            if a.get("rankdir"):
                parts.append(f"dir={str(a['rankdir']).upper()}")
            lines = ["  " * indent + " ".join(parts) + " {"]
            for n in g.order:
                if g.node_group[n] == gid:
                    lines.append(node_line(n, indent + 1))
            for c in g.group_order:
                if g.groups[c]["parent"] == gid:
                    lines += group_block(c, indent + 1)
            lines.append("  " * indent + "}")
            return lines

        for n in g.order:
            if g.node_group[n] is None:
                self.out.append(node_line(n, 0))
        for gid in g.group_order:
            if g.groups[gid]["parent"] is None:
                self.out += group_block(gid, 0)
        for s, d, a in g.edges:
            arrow, extra = self.edge_attrs(a)
            parts = [ids[s], arrow, ids[d]]
            lab = a.get("label") or a.get("xlabel")
            if lab:
                parts.append(self.q(lab))
            self.out.append(" ".join(parts + extra))
        if ranks and g.groups:
            g.notes.append("rank=same inside clusters is approximate")
        return "\n".join(l for l in self.out if l is not None) + "\n"


def convert(dot: str) -> str:
    return Emitter(Parser(dot).parse()).emit()


class MarkdownConverter:
    BLOCK = re.compile(r"^```dot[ \t]*\n(.*?)^```[ \t]*$", re.S | re.M)

    def __init__(self, path: Path):
        self.path = path

    def run(self, write: bool) -> tuple[int, list[str]]:
        text = self.path.read_text(encoding="utf-8")
        errors, n = [], 0

        def sub(m):
            nonlocal n
            try:
                pdg = convert(m.group(1))
            except Exception as e:  # keep the block, report it
                errors.append(f"{self.path}: block at char {m.start()}: {e}")
                return m.group(0)
            n += 1
            return "```pdg\n" + pdg + "```"

        new = self.BLOCK.sub(sub, text)
        if write and n:
            self.path.write_text(new, encoding="utf-8")
        elif not write:
            sys.stdout.write(new)
        return n, errors


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="+", type=Path)
    p.add_argument("--write", action="store_true", help="rewrite Markdown files in place")
    args = p.parse_args()
    total, errs = 0, []
    for f in args.files:
        if f.suffix == ".md":
            n, e = MarkdownConverter(f).run(args.write)
            total += n
            errs += e
            print(f"{f}: {n} block(s) converted", file=sys.stderr)
        else:
            sys.stdout.write(convert(f.read_text(encoding="utf-8")))
    for e in errs:
        print("ERROR", e, file=sys.stderr)
    print(f"total converted: {total}, failed: {len(errs)}", file=sys.stderr)


if __name__ == "__main__":
    main()
