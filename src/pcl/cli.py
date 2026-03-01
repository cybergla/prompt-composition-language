"""PCL CLI — compile, render, check, watch subcommands."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import cbor2
import typer

from .compiler import (
    Conditional,
    VarRef,
    compile as pcl_compile,
    render as pcl_render,
    serialize as pcl_serialize,
    deserialize as pcl_deserialize,
)
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


def _dump_segments(segments: list, indent: int = 0) -> str:
    """Format IR segments as a human-readable tree."""
    prefix = "  " * indent
    parts: list[str] = []
    for seg in segments:
        if isinstance(seg, str):
            if seg == "\n":
                continue
            parts.append(f"{prefix}TEXT  {seg!r}")
        elif isinstance(seg, VarRef):
            default = f" | {seg.default}" if seg.default is not None else ""
            parts.append(f"{prefix}VAR   ${{{seg.name}{default}}}")
        elif isinstance(seg, Conditional):
            neg = "not " if seg.negated else ""
            parts.append(f"{prefix}IF    {neg}{seg.variable}:")
            parts.append(_dump_segments(seg.body, indent + 1))
    return "\n".join(parts)


@app.command()
def compile(
    file: str = typer.Argument(..., help="Path to .pcl file"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Write compiled IR to .pclc file"),
) -> None:
    """Compile a .pcl file and dump the intermediate representation."""
    path = Path(file)
    try:
        template = pcl_compile(path)
    except (PCLError, FileNotFoundError) as exc:
        _abort_with_error(str(exc))
    if output is not None:
        out_path = Path(output)
        out_path.write_bytes(cbor2.dumps(pcl_serialize(template)))
        typer.echo(f"Compiled to {out_path}")
        return
    if template.metadata:
        typer.echo("Metadata:")
        for key, value in template.metadata.items():
            typer.echo(f"  {key}: {value}")
        typer.echo()
    typer.echo("Segments:")
    typer.echo(_dump_segments(template.segments))


# ---------------------------------------------------------------------------
# pcl render
# ---------------------------------------------------------------------------


@app.command()
def render(
    file: str = typer.Argument(..., help="Path to .pcl or .pclc file"),
    var: list[str] = typer.Option([], "--var", help="Variable as key=value"),
) -> None:
    """Render a .pcl or .pclc file with variables and print the output."""
    path = Path(file)
    variables = _parse_vars(var)
    try:
        if path.suffix == ".pclc":
            try:
                data = cbor2.loads(path.read_bytes())
            except FileNotFoundError:
                _abort_with_error(f"File not found: {path}")
            except cbor2.CBORDecodeError as exc:
                _abort_with_error(f"Invalid .pclc file: {exc}")
            template = pcl_deserialize(data)
            result = pcl_render(template, variables=variables)
        else:
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
