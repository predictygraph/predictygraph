# Nodal DSL — specification v0.1 (draft)

Nodal is a small, line-oriented text format for diagrams (flowcharts, architecture
graphs, trees, grids). Design goals:

1. **Readable diffs** — one statement per line, no XML, no coordinates unless you ask.
2. **Layout is explicit and local** — every container (graph or group) chooses its
   own layout ("balancing style"). A layered flow can contain a grid, which can
   contain a radial cluster. Changing one group never reshuffles the others.
3. **Styling is plain CSS** — a small, documented subset resolved by the tool itself.
   Output is static SVG with presentation attributes; no browser, no JS.
4. **Language agnostic** — the grammar below is the contract. Python is only the
   reference implementation.

File extension: `.nod`. Encoding: UTF-8.

## 1. Lexical rules

- Comments: `#` followed by a space (or end of line), at line start or after
  whitespace. `#fff` and `#id` are therefore never comments. Not applied inside `css { }`.
- Strings: `"..."` with `\"`, `\\`, `\n` escapes. `\n` in labels makes a line break.
- Identifiers: `[A-Za-z_][A-Za-z0-9_-]*` (case-sensitive).
- Classes: `.name` — attach CSS classes.
- Attributes: `key=value` where value is an identifier, number, string, or `x,y`.
- Statements end at newline. `{` opens a block, `}` closes it (own line or end of line).

## 2. Statements

```
graph   [attrs]                    # optional header, must be first statement
css     "file.css"                 # external stylesheet (relative to the .nod file)
css { ...raw css... }              # inline stylesheet (braces must balance)
default node|edge|group [attrs]    # defaults for everything after this line in scope

ID ["Label"] [.class...] [attrs]   # node
A ARROW B [ARROW C...] ["label"] [.class...] [attrs]   # edge chain
A, B ARROW C, D                    # fan-out/fan-in (cartesian product)
group ID ["Label"] [.class...] [attrs] {   # container with its own layout
  ...statements...
}
```

Nodes referenced in an edge but never declared are created implicitly in the
**current scope** with their ID as label. A node belongs to the scope where it is
first declared or referenced — so declare nodes inside their group first and connect
them from anywhere.

## 3. Edges

Arrow token = optional `<`, a body of `-`, `=` or `.` characters, optional `>`
(a body without any head needs 2+ chars).

- Body `-` solid, `=` thick (width x2.5), `.` dashed (first char decides).
- `>` at the end: arrowhead at the target; `<` at the start: arrowhead at the source.

Examples: `a -> b`, `a <-> b`, `a -- b` (no heads), `a ==> b`, `a <.. b`.

Per-edge attributes override arrow defaults:

- `width=3` — stroke width in px
- `arrow=none|end|start|both` — overrides what the token says
- `head=triangle|open|diamond|dot|bar` — arrowhead shape
- `head-size=N` — arrowhead length in px (default grows with width: 6 + 2.2 x width, max 18).
  Heads are drawn as geometry, not SVG markers: the tip sits exactly on the target
  outline, the stroke stops at the head's base, and the head is aligned with the flow axis.
- `route=straight|ortho|curve|bend` — routing for this edge
  - `curve`: full S-shaped bezier.
  - `bend`: straight in the middle, rounded only at the ends. The edge leaves and enters
    nodes along the flow axis, runs `stub=` px, then bends with corner `radius=` (default 12)
    into a straight diagonal.
  - `ortho`: right angles; `radius=` rounds the corners (default 6).
- `radius=N`, `stub=N` — bend tuning (also graph-wide and as CSS `radius:` / `stub:` on `edge`)
- `weight=N` — how strongly a layered layout keeps the edge short/straight (default 1)
- `constraint=false` — the edge is drawn but ignored by layout

Graph-wide defaults: `graph edge-width=1.5 arrow=end head=triangle route=curve` or
`default edge width=2`.

## 4. Nodes

Attributes:

- `shape=box|square|round|pill|circle|ellipse|diamond|hexagon|cylinder|note|none|image`
  (`square` = box forced to equal width and height)

Edge endpoints may be node IDs or group IDs. `a -> pool` attaches to the group's outer box.
- `image=path.svg|path.png` — makes the node an image leaf. Default `shape=image`
  (no box, label below). With an explicit shape the image sits inside the box above the label.
- `img-width=48 img-height=48` — image size (defaults: intrinsic, max 96px).
- `width=W height=H` — minimum size.
- `at=x,y` — position, only honoured by `layout=fixed`.
- `rank=N` (layered) / `row=R col=C` (grid) — pin a slot.

## 5. Layouts (balancing styles)

Every container takes `layout=` and its own options. Groups are laid out first
(inside-out), then treated as a single box by their parent. Edges between members
of different groups are projected onto the group boxes for the parent's layout, then
routed between real nodes.

- `layout=layered` (default) — rank-based flow (Sugiyama-style).
  - `dir=TB|BT|LR|RL`
  - `balance=center|start|end|median` — `center` centres each rank, `median` pulls
    nodes towards their neighbours (dot-like), `start`/`end` justify ranks.
  - `rank-gap=60 node-gap=30`
  - `order=source|auto` — `source` keeps file order inside each rank (no
    crossing minimisation, the most stable); `auto` minimises crossings.
- `layout=grid` — `cols=N` (or `rows=N`), `align=center|start|end`, `gap=24`.
- `layout=row` / `layout=column` — single line, `align=`, `gap=`.
- `layout=radial` — `center=ID` (default first child), `radius=auto|N`.
- `layout=fixed` — children use `at=x,y` (top-left, relative to the container).

Default for a group is `layout=row` when it has no internal edges, else `layered`
(set explicitly for stable results).

## 6. Styling (CSS subset)

Selectors: type (`node`, `edge`, `group`, `graph`, `label`), `.class`, `#id`,
compounds (`node.db`, `edge.hot`), group descendant (`#cluster node`). Specificity
and source order follow CSS. Order of precedence:
built-in defaults < stylesheets < `default` statements < inline attributes.

Supported properties:

- Box: `fill`, `stroke`, `stroke-width`, `stroke-dasharray`, `border-radius`,
  `padding`, `min-width`, `min-height`, `opacity`, `shadow` (`none|soft`)
- Text: `color`, `font-family`, `font-size`, `font-weight`, `font-style`, `text-align`
- Edge: `stroke`, `stroke-width`, `stroke-dasharray`, `arrow`, `head`, `route`
- Group: everything a node has plus `label-position: top|bottom`
- Custom properties `--name: value` and `var(--name)` are supported, so slidr themes
  can share palettes.

## 7. Output contract

The renderer emits a standalone SVG 1.1 file. Every element carries
`class="nodal-node <classes>"` and `id`, styling is also written as presentation
attributes so the file looks the same in rsvg, Inkscape, WeasyPrint, PowerPoint or
a browser. Text width is measured with the actual font file (no browser).

## 8. Example

```nod
graph dir=LR balance=median route=ortho edge-width=1.5
css "theme.css"

user "Data scientist" image=icons/user.svg
group k8s "Kubernetes cluster" layout=layered dir=TB {
  api "kube-apiserver"
  sched "HAMi scheduler" .hami
  api -> sched
}
group gpus "GPU nodes" layout=grid cols=2 {
  g0 "A100" ; g1 "A100" ; g2 "H100" ; g3 "H100"
}
user -> api "submit pod"
sched ==> gpus "bind" .hot
```

(`;` may separate statements on one line.)
