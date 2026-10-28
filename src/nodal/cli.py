"""nodal CLI: .nod -> Scene IR -> .svg (animated or static) or .png (APNG)."""
from __future__ import annotations

from pathlib import Path

import typer

from . import list_themes, scene_from_file, write_apng, write_svg

app = typer.Typer(add_completion=False, help="Render Nodal diagrams to SVG or APNG.")


@app.command()
def main(
    src: Path = typer.Argument(None, help="Input .nod file"),
    out: Path | None = typer.Option(None, "-o", "--out", help="Output .svg or .png (default: <src>.svg)"),
    css: list[Path] = typer.Option([], "--css", help="Extra stylesheet(s), applied after the file's own"),
    theme: str | None = typer.Option(None, "--theme", help="Theme name or .toml path (overrides graph theme=)"),
    themes: bool = typer.Option(False, "--list-themes", help="List bundled themes and exit"),
    check: bool = typer.Option(False, "--check", help="Parse, lay out and route only; report errors"),
    static: bool = typer.Option(False, "--static", help="SVG without animation (first frame)"),
    at: float | None = typer.Option(None, "--at", help="SVG frozen at this time (seconds)"),
    fps: int = typer.Option(20, "--fps", help="APNG frames per second"),
    seconds: float | None = typer.Option(None, "--seconds", help="APNG length (default: one full loop)"),
    scale: float = typer.Option(2.0, "--scale", help="APNG pixel scale"),
    allow_outside: bool = typer.Option(False, "--allow-outside",
                                       help="Let image= and css \"...\" read files outside the input's directory"),
) -> None:
    if themes:
        typer.echo("\n".join(list_themes()))
        return
    if src is None or not src.exists():
        typer.echo("missing input file", err=True)
        raise typer.Exit(2)
    target = out or src.with_suffix(".svg")
    try:
        scene = scene_from_file(src, [p.read_text() for p in css], theme, allow_outside)
        if check:
            typer.echo(f"{src}: ok")
            return
        if target.suffix.lower() in (".png", ".apng"):
            write_apng(scene, target, fps, scale, seconds)
        else:
            t = at if at is not None else (0.0 if static else None)
            target.write_text(write_svg(scene, t), encoding="utf-8")
    except (ValueError, OSError, RuntimeError) as exc:
        typer.echo(f"{src}: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(str(target))
