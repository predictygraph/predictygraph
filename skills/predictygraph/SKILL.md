---
name: predictygraph
description: Draw architecture diagrams, flowcharts and system maps as predictygraph (.pdg) files and render them to SVG or PNG. Use when someone asks for a diagram, a box-and-arrow picture of a system, a flowchart, or a figure for slides or docs, or when they share a .pdg file.
version: 0.2.3
license: GPL-3.0-or-later
metadata:
  hermes:
    tags: [diagrams, graphs, svg, architecture, flowchart, slides]
    category: creative
---

# predictygraph

predictygraph turns a short text file (`.pdg`) into an SVG or PNG diagram. Each group of
boxes picks its own layout, so changing one part of a diagram never reshuffles the rest.

## When to use

- Someone wants an architecture diagram, a flowchart, a request path, a layer stack or a
  module tree.
- Someone has a `.pdg` file and wants it rendered, changed or fixed.
- Someone wants a diagram for slides: decktile renders ` ```pdg ` blocks directly.

For sequence diagrams, Gantt charts or pie charts, use a different tool; predictygraph
has none of those.

## Setup

```bash
uv tool install "predictygraph[apng]"   # or: pipx install "predictygraph[apng]"
pdg --help
```

`[apng]` adds PNG output (it needs the cairo library, which Linux desktops and CI images
usually have). SVG output needs nothing extra.

## Procedure

1. **Sketch the structure first.** List the boxes, group them into panels (one panel per
   layer, team, machine or step), and decide each panel's direction: `layout=row`
   (left to right) or `layout=column` (top to bottom). Use `layout=layered` (the
   default when a group has edges inside it) for a flow where arrows decide the order.
2. **Write the file.** Start from the template below, or from the closest example in
   `references/examples.md`. The full syntax is in `references/syntax.md`.
3. **Check it:** `pdg diagram.pdg --check` reports syntax errors with line numbers.
4. **Render:** `pdg diagram.pdg -o diagram.svg`. For chat or email, a small PNG:
   `pdg diagram.pdg -o diagram.png --width 900 --colors 64` (about 30 KB).
5. **Look at the result** (open the PNG, or ask a vision model) and fix what is wrong;
   the pitfalls below cover the usual problems.

## Template

```pdg
graph layout=column align=stretch gap=12 theme=hami caption="What this diagram shows"

group front "Front end" layout=row gap=40 {
  web "Web app" sub="React"
  cdn "CDN" sub="static files" .blue
}
group back "Back end" layout=row gap=40 {
  api "API" sub="checks the token" .green
  worker "Worker" sub="sends e-mails" .green
}
group data "Data" layout=row {
  db "PostgreSQL" shape=cylinder align-x=api   # straight under the API
}

web -> cdn
web -> api "REST"
api -> worker "jobs"
api -> db "SQL"

legend .green "ours"
legend .blue "third party"
```

## The features people ask for most

- **Two lines in a box:** `api "API" sub="checks the token"`. The second line is
  smaller and grey.
- **Numbered steps:** `graph steps=auto` numbers every arrow in file order;
  `a -> b step=3` sets one by hand.
- **Equal-width layers / equal-height panels:** `align=stretch` on the parent.
- **Line up boxes in different panels:** `align-x=ID` centres a box (or a group) over
  another one, so the arrow between them is straight.
- **A note over several boxes:** `bracket a, d "note"` draws a curly bracket beside them.
- **Key and caption:** `legend .green "our services"`, `graph caption="..."`.
- **Panel title on the side:** CSS `group { label-position: left; }`.
- **A coloured strip on a box:** CSS `node.green { accent-bar: 4px var(--green); }`.
- **Themes:** `graph theme=nord` (list them with `pdg --list-themes`); `hami` gives the
  look of the HAMi docs.

## Pitfalls

- **An arrow cuts through a box:** pin its sides with `exit=left enter=left`; matching
  sides draw a C-shaped route around everything in between.
- **A label covers a box or is cut off:** labels on arrows inside a `layout=row`
  widen that gap automatically. Elsewhere, shorten the label or raise `gap=`.
- **Text spills out of boxes in someone else's viewer:** their computer drew the text in
  a wider font. Render with `--target web` for files you share; it sizes every box for
  the widest font in the list.
- **Edges are tangled:** split the diagram into more panels. Each panel lays out on its
  own, and arrows between panels route around them.
- **`align-x` didn't move a box all the way:** it only moves within its own panel's free
  space, never past the panel edge. Widen the panel (`align=stretch` on the parent) or
  add `gap=`.
- **Labels with `#`:** a `#` followed by a space starts a comment. Inside quotes it is
  fine: `"issue #42"`.

## Verification

- `pdg diagram.pdg --check` prints `ok`.
- The rendered picture has no text outside boxes, no arrow crossing a box, and every
  box the user asked for.
