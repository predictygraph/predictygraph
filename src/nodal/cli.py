"""nodal CLI: .nod -> .svg (optionally .png/.pdf)."""
from __future__ import annotations

from pathlib import Path

import typer

from . import render_file

app = typer.Typer(add_completion=False, help="Render Nodal diagrams to static SVG.")


@app.command()
def main(
    src: Path = typer.Argument(..., exists=True, help="Input .nod file"),
    out: Path | None = typer.Option(None, "-o", "--out", help="Output .svg (default: next to input)"),
    css: list[Path] = typer.Option([], "--css", help="Extra stylesheet(s), applied after the file's own"),
    check: bool = typer.Option(False, "--check", help="Parse and lay out only; report errors"),
) -> None:
    try:
        svg = render_file(src, [p.read_text() for p in css])
    except ValueError as exc:
        typer.echo(f"{src}: {exc}", err=True)
        raise typer.Exit(1) from exc
    if check:
        typer.echo(f"{src}: ok")
        return
    target = out or src.with_suffix(".svg")
    target.write_text(svg, encoding="utf-8")
    typer.echo(str(target))
