# nodal

Readable diagram DSL with per-group layouts ("balancing styles"), plain-CSS styling,
and static SVG output (no browser). Spec: [docs/SPEC.md](docs/SPEC.md).

```bash
uv run nodal examples/hami_flow.nod          # -> examples/hami_flow.svg
uv run nodal diagram.nod --css theme.css -o out.svg
uv run nodal diagram.nod --check             # validate only
```
