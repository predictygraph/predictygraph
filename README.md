<!--
SPDX-FileCopyrightText: 2026 The predictygraph Authors

SPDX-License-Identifier: GPL-3.0-or-later
-->

# predictygraph

**Predictable graphs.** A readable diagram DSL with per-group layouts ("balancing styles"),
plain-CSS styling, and static or animated SVG/APNG output (no browser).
Spec: [docs/SPEC.md](docs/SPEC.md). Docs: [predictygraph.github.io](https://predictygraph.github.io/).
Editor support: [tree-sitter-pdg](https://github.com/predictygraph/tree-sitter-pdg).
Rendered examples and the gallery: [predictygraph.github.io](https://predictygraph.github.io/). This repo keeps
only `.pdg` sources; images live in the docs repo (git-lfs).

```bash
uv run pdg examples/hami_flow.pdg                    # -> examples/hami_flow.svg (not committed)
uv run pdg diagram.pdg --css theme.css -o out.svg
uv run pdg diagram.pdg -o out.png                    # animated PNG (APNG)
uv run pdg diagram.pdg --check                       # validate only
uv run pdg diagram.pdg --target web                  # size labels to fit any browser font
```

`pdg` is the short alias of the `predictygraph` command.

## Credits

This project stands on the shoulders of two giants.

**[Graphviz](https://graphviz.org/) (dot)** taught a generation that diagrams can be
text. Its layered layout algorithm is still the reference for graph drawing, and
we are grateful for decades of work on it. But dot optimises for the whole graph
at once: you describe nodes and edges, and the engine decides where they go.
Nudging one cluster without disturbing the rest means fighting `rank`, `weight`
and invisible edges. Styling lives in attributes rather than CSS, and the output
often looks like a paper figure rather than a slide.

**[Mermaid](https://mermaid.js.org/)** made text diagrams mainstream by putting
them in Markdown, READMEs and docs sites. Its syntax is friendly and we borrowed
from its spirit. But it renders through a browser and JavaScript, leaves little
control over layout, and the same source can render differently across versions
and hosts.

predictygraph keeps what we love from both (diagrams as readable text) and adds what we
missed: per-group layouts, plain-CSS styling, and deterministic static SVG with no
browser in the loop.
