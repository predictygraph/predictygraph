# predictygraph

Readable diagram DSL with per-group layouts ("balancing styles"), plain-CSS styling,
and static SVG output (no browser). Spec: [docs/SPEC.md](docs/SPEC.md).

```bash
uv run predictygraph examples/hami_flow.pdg          # -> examples/hami_flow.svg
uv run predictygraph diagram.pdg --css theme.css -o out.svg
uv run predictygraph diagram.pdg --check             # validate only
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

nodal keeps what we love from both (diagrams as readable text) and adds what we
missed: per-group layouts, plain-CSS styling, and deterministic static SVG with no
browser in the loop.
