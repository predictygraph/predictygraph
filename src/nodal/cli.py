"""nodal CLI: .nod -> .svg (animated or static) or animated .png (APNG)."""
from __future__ import annotations

from pathlib import Path

import typer

from . import list_themes, load_file, render_file

app = typer.Typer(add_completion=False, help="Render Nodal diagrams to SVG or APNG.")


@app.command()
def main(
    src: Path = typer.Argument(None, help="Input .nod file"),
    out: Path | None = typer.Option(None, "-o", "--out", help="Output .svg or .png (default: <src>.svg)"),
    css: list[Path] = typer.Option([], "--css", help="Extra stylesheet(s), applied after the file's own"),
    theme: str | None = typer.Option(None, "--theme", help="Theme name or .toml path (overrides graph theme=)"),
    themes: bool = typer.Option(False, "--list-themes", help="List bundled themes and exit"),
    check: bool = typer.Option(False, "--check", help="Parse and lay out only; report errors"),
    static: bool = typer.Option(False, "--static", help="SVG without animation (first frame)"),
    at: float | None = typer.Option(None, "--at", help="SVG frozen at this time (seconds)"),
    fps: int = typer.Option(20, "--fps", help="APNG frames per second"),
    seconds: float | None = typer.Option(None, "--seconds", help="APNG length (default: one full loop)"),
    scale: float = typer.Option(2.0, "--scale", help="APNG pixel scale"),
) -> None:
    if themes:
        typer.echo("\n".join(list_themes()))
        return
    if src is None or not src.exists():
        typer.echo("missing input file", err=True)
        raise typer.Exit(2)
    target = out or src.with_suffix(".svg")
    extra = [p.read_text() for p in css]
    try:
        if target.suffix.lower() in (".png", ".apng"):
            from .apng import ApngExporter
            if check:
                load_file(src, extra, theme)
            else:
                ApngExporter(load_file(src, extra, theme), fps, scale, seconds).save(target)
        else:
            t = at if at is not None else (0.0 if static else None)
            svg = render_file(src, extra, theme, t)
            if not check:
                target.write_text(svg, encoding="utf-8")
    except (ValueError, OSError, RuntimeError) as exc:
        typer.echo(f"{src}: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"{src}: ok" if check else str(target))
