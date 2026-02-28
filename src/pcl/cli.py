"""PCL CLI — compile, render, check, watch subcommands."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from .compiler import compile as pcl_compile, render as pcl_render
from .errors import PCLError

app = typer.Typer(help="PCL — Prompt Composition Language toolchain.", add_completion=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_vars(var: list[str]) -> dict:
    """Parse ['key=value', ...] into a dict, coercing 'true'/'false' to bool."""
    variables: dict = {}
    for entry in var:
        if "=" not in entry:
            typer.echo(f"Error: --var must be key=value, got {entry!r}", err=True)
            raise typer.Exit(1)
        key, value = entry.split("=", 1)
        if value.lower() == "true":
            variables[key] = True
        elif value.lower() == "false":
            variables[key] = False
        else:
            variables[key] = value
    return variables


def _abort_with_error(msg: str, exit_code: int = 1) -> None:
    typer.echo(f"Error: {msg}", err=True)
    raise typer.Exit(exit_code)


# ---------------------------------------------------------------------------
# pcl compile
# ---------------------------------------------------------------------------


@app.command()
def compile(file: str = typer.Argument(..., help="Path to .pcl file")) -> None:
    """Compile a .pcl file and print the output."""
    path = Path(file)
    try:
        result = pcl_render(path, variables={})
    except (PCLError, FileNotFoundError) as exc:
        _abort_with_error(str(exc))
    typer.echo(result, nl=False)


# ---------------------------------------------------------------------------
# pcl render
# ---------------------------------------------------------------------------


@app.command()
def render(
    file: str = typer.Argument(..., help="Path to .pcl file"),
    var: list[str] = typer.Option([], "--var", help="Variable as key=value"),
) -> None:
    """Render a .pcl file with variables and print the output."""
    path = Path(file)
    variables = _parse_vars(var)
    try:
        result = pcl_render(path, variables=variables)
    except (PCLError, FileNotFoundError) as exc:
        _abort_with_error(str(exc))
    typer.echo(result, nl=False)


# ---------------------------------------------------------------------------
# pcl check
# ---------------------------------------------------------------------------


@app.command()
def check(file: str = typer.Argument(..., help="Path to .pcl file")) -> None:
    """Validate a .pcl file without producing output. Exits 1 on error."""
    path = Path(file)
    try:
        pcl_compile(path)
    except FileNotFoundError as exc:
        _abort_with_error(str(exc), exit_code=2)
    except PCLError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1)
    typer.echo("OK")


# ---------------------------------------------------------------------------
# pcl watch
# ---------------------------------------------------------------------------


@app.command()
def watch(
    file: str = typer.Argument(..., help="Path to .pcl file"),
    var: list[str] = typer.Option([], "--var", help="Variable as key=value"),
) -> None:
    """Watch a .pcl file and recompile on change."""
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    import time

    path = Path(file).resolve()
    variables = _parse_vars(var)

    def _compile_and_print() -> None:
        try:
            result = pcl_render(path, variables=variables)
            typer.echo(result, nl=False)
        except (PCLError, FileNotFoundError) as exc:
            typer.echo(f"Error: {exc}", err=True)

    class _Handler(FileSystemEventHandler):
        def on_modified(self, event) -> None:  # type: ignore[override]
            if Path(event.src_path).resolve() == path:
                typer.echo(f"\n--- {path.name} changed ---")
                _compile_and_print()

    typer.echo(f"Watching {path} …  (Ctrl-C to stop)")
    _compile_and_print()

    observer = Observer()
    observer.schedule(_Handler(), str(path.parent), recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
