<!--
SPDX-FileCopyrightText: 2026 Reza Jelveh

SPDX-License-Identifier: Apache-2.0
-->

# predictygraph

**Predictable graphs.** A readable diagram DSL with per-group layouts ("balancing styles"),
plain-CSS styling, and static or animated SVG/APNG output (no browser).
Spec: [docs/SPEC.md](docs/SPEC.md). Docs: [predictygraph.github.io](https://predictygraph.github.io/).
Editor support: [tree-sitter-pdg](https://github.com/predictygraph/tree-sitter-pdg).
In the browser: [predictygraph-js](https://github.com/predictygraph/predictygraph-js).
Rendered examples and the gallery: [predictygraph.github.io](https://predictygraph.github.io/). This repo keeps
only `.pdg` sources; images live in the docs repo (git-lfs).

## Install

```bash
uv tool install "predictygraph[apng]"    # or: pipx install "predictygraph[apng]"
```

`[apng]` adds PNG output. `pdg` is the short alias of the `predictygraph` command.

## Use

```bash
pdg examples/annotations.pdg                     # -> examples/annotations.svg (not committed)
pdg diagram.pdg --css theme.css -o out.svg
pdg diagram.pdg -o out.png                       # PNG (animated if the diagram moves)
pdg diagram.pdg --check                          # validate only
pdg diagram.pdg -o d.png --width 1000 --colors 64   # small PNG for chat
pdg diagram.pdg --target web                     # size labels to fit any browser font
```

From a checkout, prefix these with `uv run`. Start with
[examples/annotations.pdg](examples/annotations.pdg): one small diagram that uses every
annotation feature, with a comment for each.

## Agent skill

[skills/predictygraph](skills/predictygraph) teaches an AI agent to write, render and
check `.pdg` diagrams.

```bash
# Hermes Agent
hermes skills install https://raw.githubusercontent.com/predictygraph/predictygraph/master/skills/predictygraph/SKILL.md
# Claude Code and other agents that read SKILL.md folders: copy the folder
cp -r skills/predictygraph ~/.claude/skills/
```

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

## License

Apache-2.0, see [LICENSE](LICENSE). Forks must keep [NOTICE](NOTICE). Bundled fonts keep their own licences in [fonts/licenses](src/predictygraph/fonts/licenses).
