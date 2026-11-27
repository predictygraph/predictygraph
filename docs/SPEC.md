<!--
SPDX-FileCopyrightText: 2026 Reza Jelveh

SPDX-License-Identifier: Apache-2.0
-->

# Predictygraph DSL: specification v0.2 (draft)

Predictygraph is a small, line-oriented text format for diagrams (flowcharts, architecture
graphs, trees, grids). Design goals:

1. **Readable diffs**: one statement per line, no XML, no coordinates unless you ask.
2. **Layout is explicit and local**: every container (graph or group) chooses its
   own layout ("balancing style"). A layered flow can contain a grid, which can
   contain a radial cluster. Changing one group never reshuffles the others.
3. **Styling is plain CSS**: a small, documented subset resolved by the tool itself.
   Output is static SVG with presentation attributes; no browser, no JS.
4. **Language agnostic**: the grammar below is the contract. Python is only the
   reference implementation.

File extension: `.pdg`. Encoding: UTF-8.

## 1. Lexical rules

- Comments: `#` followed by a space (or end of line), at line start or after
  whitespace. `#fff` and `#id` are therefore never comments. Not applied inside `css { }`.
- Strings: `"..."` with `\"`, `\\`, `\n` escapes. `\n` in labels makes a line break.
- Identifiers: `[A-Za-z_][A-Za-z0-9_-]*` (case-sensitive).
- Classes: `.name` attaches a CSS class.
- Attributes: `key=value` where value is an identifier, number, string, or `x,y`.
  No spaces around `=` (only `let NAME = VALUE` allows them).
- Statements end at newline or `;`, also right after an unquoted attribute value
  (`a "" width=9; b "B"`). `{` opens a block, `}` closes it (own line or end of line).
- Keywords (`graph css default group let def use bracket legend node edge`) only count
  at the start of a statement; elsewhere they are ordinary IDs (`group node { ... }`).

Editor grammars that follow this section:
[tree-sitter-pdg](https://github.com/predictygraph/tree-sitter-pdg) and
[lezer-pdg](https://github.com/predictygraph/lezer-pdg) (CodeMirror 6).

## 2. Statements

```
graph   [attrs]                    # optional header, must be first statement
css     "file.css"                 # external stylesheet (relative to the .pdg file)
css { ...raw css... }              # inline stylesheet (braces must balance)
default node|edge|group [attrs]    # defaults for everything after this line in scope

ID ["Label"] [.class...] [attrs]   # node
A ARROW B [ARROW C...] ["label"] [.class...] [attrs]   # edge chain
A, B ARROW C, D                    # fan-out/fan-in (cartesian product)
group ID ["Label"] [.class...] [attrs] {   # container with its own layout
  ...statements...
}
bracket A[, B...] ["note"] [.class...] [attrs]   # side bracket (top level, see 4.1)
legend "Key"                                     # legend title (top level)
legend .class... ["Label"] [attrs]               # legend entry (top level)
```

Nodes referenced in an edge but never declared are created implicitly in the
**current scope** with their ID as label. A node belongs to the scope where it is
first declared or referenced, so declare nodes inside their group first and connect
them from anywhere.

### 2.1 Variables and reusable blocks

```
let NAME = VALUE                   # value variable, VALUE = identifier, number, string or x,y
def NAME [PARAM[=DEFAULT]...] {    # reusable block
  ...statements...
}
use NAME ID ["Label"] [.class...] [PARAM=VALUE...] [attrs]   # place a copy of the block
```

- `$NAME` is replaced by the variable's value anywhere a value can stand: labels,
  attribute values, class names. Inside strings write `"${NAME}"`. An unknown `$NAME`
  is an error. Variables follow scope: one set in a group is visible only in that group.
- `def` statements produce nothing. `use` places one copy of the block as a `group`
  with the given `ID`, label, classes and attrs, so it gets its own layout like any group.
- Inside a block, `$ID` and `$LABEL` refer to the `use` line's ID and label, and each
  parameter is a variable. Parameters without a default must be given on `use`.
- **IDs inside a block are local.** A copy's node `cpu` becomes `ID-cpu`, so two copies
  never clash. Connect to it from outside with that full name (`node1-cpu -> switch`).
- `def` may appear anywhere before its first `use`; a block may `use` other blocks but
  not itself.

```
let accent = "#3939D8"

def server gpus=2 {
  cpu "CPU"
  gpu "GPU x${gpus}" fill=$accent
  cpu -> gpu
}

group rack layout=row {
  use server node1 "Node 1"
  use server node2 "Node 2" gpus=8
}
scheduler -> node1-cpu, node2-cpu
```

## 3. Edges

Arrow token = optional `<`, a body of `-`, `=` or `.` characters, optional `>`
(a body without any head needs 2+ chars).

- Body `-` solid, `=` thick (width x2.5), `.` dashed (first char decides).
- `>` at the end: arrowhead at the target; `<` at the start: arrowhead at the source.

Examples: `a -> b`, `a <-> b`, `a -- b` (no heads), `a ==> b`, `a <.. b`.

Per-edge attributes override arrow defaults:

- `width=3`: stroke width in px
- `arrow=none|end|start|both`: overrides what the token says
- `head=triangle|open|diamond|dot|bar`: arrowhead shape
- `head-size=N`: arrowhead length in px (default grows with width: 6 + 2.2 x width, max 18).
  Heads are drawn as geometry, not SVG markers: the tip sits exactly on the target
  outline, the stroke stops at the head's base, and the head is aligned with the flow axis.
- `route=straight|ortho|curve|bend`: routing for this edge
  - `curve`: full S-shaped bezier.
  - `bend`: straight in the middle, rounded only at the ends. The edge leaves and enters
    nodes along the flow axis, runs `stub=` px, then bends with corner `radius=` (default 12)
    into a straight diagonal.
  - `ortho`: right angles; `radius=` rounds the corners (default 6).
- `radius=N`, `stub=N`: bend tuning (also graph-wide and as CSS `radius:` / `stub:` on `edge`)
- `via="x,y x,y ..."`: fixed bend points (pairs split on spaces or `;`), in the root's
  `at=` frame. The edge runs straight through them; it leaves and enters a node straight
  out of the side facing the nearest point when that point lines up with the node (else
  towards its centre). `radius=` rounds the bends (default: sharp). Works in any layout;
  the router leaves via edges alone. Edges sharing a bus just repeat its points.
- `diagonal=N|none|always`: when a bent edge may use one slanted segment instead of a
  right-angle jog. Every `bend`/`ortho` edge is: stub along the flow axis, one jog
  sideways, stub into the target. The jog is diagonal only if the sideways offset is at
  most N px **and** the slant fits between the two stubs at `diagonal-angle`; otherwise
  it is a perpendicular run (Z shape). Aligned ports are always one straight line.
  Default: `40` for `route=bend`, `none` for `route=ortho`. `always` steepens the angle
  as needed so every jog is diagonal.
- `diagonal-angle=45`: slant angle in degrees from the flow axis (10 to 80; 45 = octilinear)
- `fan=spread`: edges leaving (or entering) one side of a node use separate ports spread
  along that side, turn right after their stub and slant at `diagonal-angle`, so a
  fan-out reads as parallel branches instead of merging into one ortho bus.
  A spread branch that already ends within 24px of level with its target is snapped
  straight (one per source): the column/row gap between sources and the target's rank
  shift to line it up, so no hand-tuned `gap=`/`padding` is needed.
- Both keys work on edges, groups (nearest group wins), the `graph` line and in CSS.
- **Lanes:** when the sideways runs of different edges would land on the same line and
  overlap, they are spread into parallel lanes (9 px apart, ordered so they don't cross).
  Edges sharing a source or target *and* the same look (body, dash, colour, classes) are
  a deliberate bus and stay merged; a dashed `..>` path into the same node is a
  distinct trace and gets its own lane.
- `exit=top|bottom|left|right`, `enter=...`: pin the side an edge leaves/enters (port at the
  side's middle). Mixed vertical/horizontal sides draw an L with one rounded corner. The same
  side at both ends (`exit=left enter=left`) draws a C that goes around every box between.

Automatic routing rules (layered layouts):
- Edges between the same two nodes are offset in parallel; `A <-> B` draws one double-headed edge.
- Ortho edges sharing a target (fan-in) or source (fan-out) turn at one common level, forming a bus.
  An edge whose boxes overlap usually runs straight instead (through the narrower box's
  centre when one box spans the other); when that straight run would
  cross a sibling's bend, the whole fan leaves from one point and merges into the bus.
- Curved edges sharing a side of a node (fan-out or fan-in) swing at one common level, so a fan
  to targets at different distances does not cross itself.
- Rectangular nodes that overlap on the cross axis are joined by a single straight line (no jog).
- `weight=N`: how strongly a layered layout keeps the edge short/straight (default 1)
- `constraint=false`: the edge is drawn but ignored by layout

Graph-wide defaults: `graph edge-width=1.5 arrow=end head=triangle route=curve` or
`default edge width=2`.

## 4. Nodes

Attributes:

- `shape=box|square|round|pill|circle|ellipse|diamond|hexagon|cylinder|note|none|image`
  (`square` = box forced to equal width and height)

Edge endpoints may be node IDs or group IDs. `a -> pool` attaches to the group's outer box.
- `image=path.svg|path.png`: makes the node an image leaf. Default `shape=image`
  (no box, label below). With an explicit shape the image sits inside the box above the label.
- `img-width=48 img-height=48`: image size (defaults: intrinsic, max 96px).
- `icon=user`: a [Lucide](https://lucide.dev/icons) icon instead of an image file
  (needs `pip install 'predictygraph[icons]'`). It takes the node's `fill`, `stroke` and
  `stroke-width`; default size 48px, change it with `img-width`/`img-height`.
- On an edge, `image=logo.png img-width=48` places a badge beside the middle of the
  edge's longest run (below a horizontal run, right of a vertical one).
- `label-at=start|end` on a bent edge puts the label over its first or last horizontal
  run, with no background patch (draw.io style). Default: the run into the target.
- `width=W height=H`: minimum size, on nodes and groups (CSS `width`/`height` or
  `min-width`/`min-height` do the same). A group made wider keeps its content centred,
  or shares the space out with `justify=fill`.
- `at=x,y`: position, only honoured by `layout=fixed`.
- `layer=back` (or CSS `layer: back`): draw the node under the edges, like a group.
  For coloured backgrounds and panels that lines run across.
- `rank=N` (layered) / `row=R col=C` (grid): pin a slot.
- `align-x=ID`: after layout, centre this node or group horizontally on another item,
  even one in a different panel (line a box up with the one it calls below). It only
  moves inside its parent's content box and never past a sibling, so nothing overlaps.
- `sub="second line"`: secondary text under the label, on nodes and groups. Styled with
  the `sub` selector (default: grey, 0.85em, never bold); `node.x sub { ... }` targets one
  class. `\n` makes several lines.

### 4.1 Annotations

- **Steps:** `a -> b step=3` draws a numbered circle for the edge: just left of the edge
  label when there is one; otherwise on the line a third of the way along, or, when the
  edge is too short for that (three circle widths), beside its middle, clear of any box.
  Column gaps with a numbered edge widen to fit the circle. `graph steps=auto`
  numbers every edge without its own `step=` in file order. Styled with `step`
  (`fill` is the circle, `color` the number).
- **Legend:** `legend "Key"` names the box; `legend .green "HAMi component"` adds an
  entry whose swatch is styled like a node with those classes. Drawn under the diagram;
  top level only, at most 64 entries. Styled with `legend`.
- **Caption:** `graph caption="Figure 1: ..."` draws a line under the diagram (and the
  legend). Styled with `caption` (default: grey, italic, centred).
- **Accent bar:** CSS `accent-bar: 4px #16a34a` draws a strip inside the box edge and
  widens the box by its width; `accent-side: left|right`. `accent-bar: none` removes it.
- **Header band:** CSS `title-fill: #dbeafe` on a group fills a strip behind its title
  and subtitle. Ignored with `label-position: bottom`.
- **Vertical panel label:** CSS `label-position: left` on a group turns its title 90°
  and puts it in a column at the panel's left edge. Padding moves the content, not the
  label, so a left `padding` makes room for an edge to pass between them.
- **Side brackets:** `bracket a, b "note"` draws a curly bracket right of the diagram
  from the top of the highest listed item to the bottom of the lowest, with the note
  beside it. Overlapping brackets stack outward, shorter spans nearest the diagram.
  Top level only; styled with `bracket` (`stroke`, `stroke-width`, text keys).

Not yet supported: highlight boxes that don't change the layout, and badges on node
corners.

## 5. Layouts (balancing styles)

Every container takes `layout=` and its own options. Groups are laid out first
(inside-out), then treated as a single box by their parent. Edges between members
of different groups are projected onto the group boxes for the parent's layout, then
routed between real nodes.

- `layout=layered` (default): rank-based flow (Sugiyama-style).
  - `dir=TB|BT|LR|RL`
  - `balance=center|start|end|median`: `center` centres each rank, `median` pulls
    nodes towards their neighbours (dot-like), `start`/`end` justify ranks.
  - `rank-gap=60 node-gap=30`. A labelled edge widens its rank gap so the label fits:
    by the label's height top to bottom, and in `dir=LR|RL` (where the label runs along
    the gap) to the label's width plus margins.
  - `order=source|auto`: `source` keeps file order inside each rank (no
    crossing minimisation, the most stable); `auto` minimises crossings.
- `graph padding=N`: margin around the whole diagram (default 16px; `padding=0` for none).
- `layout=grid`: `cols=N` (or `rows=N`), `align=center|start|end`, `gap=24`.
- `layout=row` / `layout=column`: single line, `align=`, `gap=`. `align=stretch` makes
  every child as wide (column) or tall (row) as the largest: equal-width tiers for
  stack diagrams. A stretched group keeps its content left; `justify=center` centres it.
  `justify=fill` on a row (column) that is made wider (taller), by `align=stretch` or
  `width=`, shares the extra space equally among its children, so cards in a tier end
  up the same size and fill it. Likewise a stretched column (row) made wider (taller)
  passes the extra on to its children, all the way down: `graph { min-width: 800px }`
  on a column of stretched tiers makes every tier 800px wide (decktile uses this to draw
  a diagram exactly as wide as its slide column).
- `.bare`: a built-in class for an invisible helper group (no fill, no outline, no
  padding), for lining items up without drawing a box.
- `layout=radial`: `center=ID` (default first child), `radius=auto|N`.
- `layout=fixed`: children use `at=x,y` (top-left, relative to the container).

Default for a group is `layout=row` when it has no internal edges, else `layered`
(set explicitly for stable results).

## 6. Styling (CSS subset)

Selectors: type (`node`, `edge`, `group`, `graph`, `label`), `.class`, `#id`,
compounds (`node.db`, `edge.hot`), group descendant (`#cluster node`). Specificity
and source order follow CSS. Order of precedence:
built-in defaults < stylesheets < `default` statements < inline attributes.

Stylesheets are layered, each overriding the one before:

1. `default.css`, shipped with predictygraph (font, sizes, neutral colours)
2. the theme (`graph theme=…` or `--theme`), if any
3. css in the `.pdg` file (`css { … }` blocks and `css "file.css"`)
4. `--css` files given on the command line

Themes only set colours and shape unless their TOML sets `[shape] font`, so the
default font survives a theme change.

### Theme files (TOML)

A theme is a TOML file (bundled ones by name, others by path or `PDG_THEME_PATH`):

- `schema = 1`, `name`, `dark = true|false`, `extends = "other"` (the child's tables
  are merged over the parent's; `css` strings stack, parent first).
- `[palette]`: named colours, each `#rrggbb` or the name of another entry
  (`edge-ink = "ink"`). Required: `bg surface fg muted border` and the hues `red orange
  yellow green cyan blue purple`. Every entry becomes a CSS variable (`var(--ink)`),
  each hue also gets a `-soft` tint, and `bg-alt` defaults to a mix of surface and bg.
  Brand colours beyond the hues go here too, so diagrams name roles, not hex codes.
- `[roles]`: which palette entry plays `accent danger node-fill node-stroke node-text
  group-fill group-stroke group-text edge edge-text`.
- `[shape]`: `radius`, `font`, `edge-width`.
- `[classes]`: named classes for nodes, groups and edges, e.g.
  `lime = { fill = "lime", color = "ink", sub = "ink-2" }`. Keys: `fill`, `stroke`
  (default: the fill), `color` (text), `title-fill`, `sub` (subtitle colour), `edge`
  (colour of `edge.lime`, default: the fill), `font-weight` and `sub-weight` (`400`,
  `"bold"`). Colours are palette names or CSS colours.
  `.lime` then works on any node, group or edge.
- Generic classes (every theme): `.label` (text without a box, regular weight),
  `.plain` (regular, fg), `.strong` (bold, fg), `.quiet` (regular, muted), `.chip`
  (surface fill, no outline), `.card` (bg fill, border hairline), `.frame` (bg fill, fg
  outline), `.outline` (no fill; colour it with `.stroke-<name>`), `.placeholder` (free
  slot: surface fill, border outline), `.ghost` (dashed muted outline, muted text),
  `.band` (fill, no outline), `.open` (group without a box; unlike `.bare` it keeps its
  padding), and `.on-<name>` for every palette entry: filled with that colour, text and
  subtitle in `on-<name>` from the palette if set (`on-mint = "white"`), else whichever
  of fg and bg contrasts more. A theme's `[classes]` and `css` may restyle any of them.
- `utilities = true`: one class per palette entry and property, so diagrams pick colours
  and weights by name without CSS: `.fill-<name>` (nodes, groups), `.stroke-<name>`,
  `.text-<name>`, `.sub-<name>` (subtitle colour), `.fill-none`, `.stroke-none`, and
  `.regular` (400), `.bold` (700), `.heavy` (900). They come after `[classes]` and the
  theme's `css`, so `a "A" .lime .text-ink .regular` is a lime box with regular ink text;
  css in the `.pdg` file still wins.
- `css`: free CSS appended after the generated rules (`var(--name)` works).
- `[seaborn]`: chart settings for decktile; ignored by pdg.

Supported properties:

- Box: `fill`, `stroke`, `stroke-width`, `stroke-dasharray`, `border-radius`,
  `padding`, `min-width`, `min-height`, `opacity`, `shadow` (`none|soft`)
- Text: `color`, `font-family`, `font-size`, `font-weight`, `font-style`, `text-align`
- Font sizes: a node without its own `font-size` takes the graph's (`graph { font-size }`,
  default 14px). `em` and `%` on nodes, groups and edges are relative to the graph's size,
  like CSS `rem`: a group's `font-size` is its title size, so it does not shrink the
  nodes inside it. On text parts (`sub`, `label`, `step`) they are relative to the owner.
  `rem` is always relative to the graph's size, on text parts too, so a theme can define
  one type scale (`--t12: 0.8rem`) that means the same everywhere.
  A host that sets the graph size (decktile: the slide's body size) so scales every
  diagram's text with one value.
- Edge: `stroke`, `stroke-width`, `stroke-dasharray`, `arrow`, `head`, `route`
- Group: everything a node has plus `label-position: top|bottom|above` (`above`: the title sits outside, over the outline)
- Custom properties `--name: value` and `var(--name)` are supported, so slidr themes
  can share palettes.

### 6.1 Render targets and fonts

Labels are measured to size their boxes, but drawn later by whatever shows the SVG.
If the viewer uses a different font from the one measured, labels overflow their boxes
(wider font) or leave gaps (narrower font). A *target* names where the SVG will be shown,
so the measurement matches:

- `host` (default): fonts installed on the machine running predictygraph; a bundled copy
  if the font is not installed.
- `linux`, `macos`, `windows`: the first font in the `font-family` list that the platform
  ships; generic families (`sans-serif`, …) resolve the way that platform does.
- `web`: every font in the list is measured and boxes fit the widest, so labels fit
  whichever font a browser picks.

Set it with `graph target=web` or `--target web` (the option wins).

The default font is `Roboto, Arial, "Helvetica Neue", sans-serif`. Roboto is not
bundled: pages showing the SVG should load it as a web font. Without it, viewers fall
back to Arial/Helvetica. Platform-specific fonts go in `@target` blocks, which apply
only when the active target is listed:

```css
graph { font-family: Roboto, Arial, "Helvetica Neue", sans-serif; }
@target linux   { graph { font-family: "DejaVu Sans", sans-serif; } }
@target windows { graph { font-family: Arial, sans-serif; } }
```

predictygraph bundles width-only copies of DejaVu Sans, Liberation Sans/Serif/Mono and
Carlito. Liberation and Carlito have the same character widths as Arial/Helvetica,
Times New Roman, Courier New and Calibri, so those are measured exactly. Any other font
with no bundled or installed copy is measured with DejaVu Sans, with a warning.

**An SVG made for one target can overflow on another.** For example, a diagram made with
`--target windows` (Arial) and opened on Linux (DejaVu Sans, 10–15% wider) has labels that
run past their boxes. Use `web` for files that are shared or published.

## 7. Animation

Animation is optional and never changes layout. The first frame (t=0) is always the
complete diagram, so static renderers (rsvg, cairosvg, WeasyPrint, PDF) stay correct.

**Edge flows**: a moving dotted pattern along the edge:

- `flow=forward`: dots travel source → target
- `flow=reverse`: target → source
- `flow=both`: two interleaved streams, one each way
- `flow=auto`: follow the arrowheads (`->` forward, `<-` reverse, `<->` both)
- `flow-speed=1.2s`: time for one dash period (default 1.2s; `ms` also accepted)
- `flow=draw`: the edge traces itself in from the source, holds, and redraws; `flow-speed`
  is the full cycle (default 3s). The t=0 frame shows the whole edge.
- `flow-dot=ring`: hollow dots (background-filled rings) instead of solid dots

`grid=40` on the `graph` line (or `graph { grid: 40; grid-color: #223; }`) draws a faint
background grid with that pitch. It is decoration only and never affects layout.
`corner-marks: 6px` on a node draws short L ticks just outside its four corners (stroke colour).

`hatch: #333` on a node fills it with 45° lines (`/`) between the fill and the outline,
e.g. reserved but unused memory. `hatch-gap: 10px` (line spacing) and `hatch-width: 1`.

`sketch: 1` gives nodes, groups and edges draw.io's hand-drawn look: each outline is
redrawn as two slightly wobbly strokes. `roughness: 1.5` sets how much (0 turns it off).
Set it per element in CSS, or for the whole diagram with `graph sketch=1 roughness=2`.
The wobble is seeded from the element ID, so a diagram always renders the same way.
Animated elements are drawn normally. See `examples/hami/with_hami.pdg`.

Without an explicit dash a flow draws round dots over a faint guide line; with a dashed
body (`..>`, `stroke-dasharray=`) that dash pattern is what moves.

**Animated borders** on nodes and groups:

- `border=march`: dashed outline that crawls around the shape ("marching ants")
- `border=pulse`: outline breathes in width and opacity
- `border=glow`: a halo ring expands and fades behind the shape
- `border-speed=1.6s`: cycle time

All four keys work as attributes, in `default node|edge|group`, on the `graph` line
(`flow-speed` only) and as CSS properties, e.g. `edge.hot { flow: forward; flow-speed: .6s; }`.
SVG output uses SMIL `<animate>` (plays in browsers); the same tracks drive APNG frames.

**Output modes (CLI):**

- `predictygraph x.pdg`: animated SVG
- `predictygraph x.pdg --static` / `--at 0.4`: SVG frozen at t=0 / t=0.4s
- `predictygraph x.pdg -o x.png`: animated PNG (APNG), one seamless loop (LCM of all cycle
  times, capped at 12s); `--fps 20 --scale 2 --seconds N` tune it. Needs `predictygraph[apng]`.

## 8. Pipeline and output contract

Same shape as slidr: one intermediate representation, many output handlers.

```
.pdg text ─parse→ AST (model.py) ─style→ ─layout ⇄ route→ Scene IR (ir.py) ─→ render/svg.py
                                          (iterated)                           └→ render/apng.py
```

- **AST** (`model.Document`): groups, nodes, edges with attributes and resolved CSS.
- **Layout** (`layout.py`): per-group placement, inside-out.
- **Routing** (`route.py`): ports, lanes, bus levels, diagonal policy. The router reports
  rank gaps too narrow for the lanes passing through them; the layout widens exactly
  those gaps and runs again (so horizontal runs keep ≥12 px clear of boxes above and
  below).
- **Scene IR** (`scene.py` → `ir.Scene`): absolute geometry, paint, text lines and
  animation tracks. Group titles are placed here: a title slides along its band to a
  span no edge crosses; if none exists the group is widened and the pipeline reruns.
  Edge labels sit on the longest straight run of their edge.
- **Writers** (`render/`): consume only the Scene IR. `svg` (animated or frozen) and
  `apng`. New targets (PNG, PDF, ODP shapes, slidr-native) add a writer, nothing else.

The SVG writer emits a standalone SVG 1.1 file. Every element carries
`class="pdg-node <classes>"` and `id`; styling is written as presentation attributes,
and title clearance uses plain geometry (no masks), so the file looks the same in rsvg,
cairosvg, Inkscape, WeasyPrint, PowerPoint or a browser. Text width is measured with
the actual font file (no browser).

## 9. Example

```pdg
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
