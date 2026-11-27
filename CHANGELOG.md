# Changelog

## 0.4.3

Theme files: `utilities = true` adds `.fill-<colour> .stroke-<colour> .text-<colour> .sub-<colour>` classes for every palette entry, plus `.fill-none .stroke-none .regular .bold .heavy`, so diagrams set colours and weights without CSS. `[classes]` entries accept `font-weight` and `sub-weight`.

## 0.4.2

Theme files: `[palette]` entries may name another entry (`lime = "green"`), so brand colours sit next to the hues; new `[classes]` table defines named colour classes for nodes, groups and edges (`lime = { fill = "lime", color = "ink", sub = "ink-2" }`). The theme TOML format is now documented in the spec.

## 0.4.1

`rem` font sizes: always relative to the graph's size, on subtitles, edge labels and step badges too (`em` there is relative to the owner). A theme can define one type scale, e.g. `graph { --t12: 0.8rem; }` and `sub { font-size: var(--t12); }`, that renders the same everywhere.

## 0.4.0

predictygraph 0.4.0: font sizes follow the diagram, so a host can scale all diagram text with one setting, and `em` works like CSS `rem`. This release also collects the layout, routing and drawing work since 0.3.0.

```
uv tool install 'predictygraph[icons]'      # or: pip install -U 'predictygraph[icons]'
```

### Breaking changes

**Nodes take the graph's font size.** A node without its own `font-size` now uses the one set on `graph`. Before, nodes were always 14px, and `graph { font-size }` only reached captions and legends. A diagram that sets `graph { font-size: 18px; }` now has 18px node text.

**`em` and `%` are relative to the graph's font size.** On nodes, groups and edges, `0.8em` means 0.8 times the graph's size, like CSS `rem`. A group's size is its title size, so it doesn't shrink the nodes inside it. Text parts (`sub`, `label`, `step`) stay relative to the element they belong to.

To keep the old sizes, set them explicitly:

```
css { node { font-size: 14px; } }
```

**decktile users:** decktile 0.4.5 always passed the slide body size to diagrams, so with this release its diagrams' node text grows (14px to 18px with the default theme). Upgrade to decktile 0.4.6, which only passes a size when the deck opts in with `pdg_scale: native`.

**Existing diagrams can move.** These layout and routing changes shift some boxes and edges in existing diagrams:

- A stretched column (row) made wider (taller), for example by `graph { min-width }` or `width=`, passes the extra space on to its children, as CSS does. Before, its content stayed at its natural size, centred.
- Edges that leave or reach the same box with `route=ortho` share one bus line; none of them takes a straight shortcut any more.
- A straight edge between a wide box and a narrow one runs through the narrow box's centre.
- Left-to-right layouts leave enough room between ranks for the full width of an edge label.
- `padding=` and the other box attributes on the `graph` line win over CSS.

**Parser:** a bare attribute value ends at `;`. `a=b; c=d` used to read `b;` as the first value.

### New

Layout:

- `width=` and `height=` on groups, and CSS `width`, `height`, `min-width`, `min-height` on nodes: a minimum box size, with the content centred.
- `justify=fill` on a row or column shares extra space among its children, smallest first, so the cards in a tier end up the same size and fill it.
- `.bare`: a built-in class for an invisible helper group (no fill, no outline, no padding).
- `layer=back` (or CSS `layer: back`) draws a node under the edges, like a group.

Edges:

- `via="x,y x,y"`: fixed bend points.
- `image=logo.png` puts a badge beside the middle of an edge.
- `label-at=start|end` puts the label on the first or last horizontal leg of a bent edge.

Drawing:

- `sketch: 1` (or `graph sketch=1 roughness=2`) gives the hand-drawn look.
- `hatch: #333` fills a node with diagonal lines, for example reserved but unused memory.
- `icon=user` uses a [Lucide](https://lucide.dev/icons) icon as a node image (`[icons]` extra).

Themes: `extends` also merges a `[seaborn]` section, so one theme file styles both diagrams and decktile charts.

### Fixes

- Curved fan-outs swing at one common level, so they no longer cross.
- `diagonal=always` slants every jog.
- Sketch style keeps sharp corners where the shape has them.

### JavaScript port

[predictygraph-js 0.2.0](https://github.com/predictygraph/predictygraph-js/releases/tag/v0.2.0) has the same breaking font-size and layout changes. Sketch, hatch, `icon=`, `via=` and `label-at` are not ported yet.

### Versions

0.3.10 was never published. 0.3.11 already contains these changes, released by mistake as a patch; 0.4.0 is the same code. To stay on the old behaviour, pin `predictygraph<0.3.11`.
