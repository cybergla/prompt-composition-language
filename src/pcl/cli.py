"""PCL CLI — Typer app with compile, render, check, watch subcommands."""
# Stub — implementation comes in Phase 5.

import typer

app = typer.Typer(help="PCL — Prompt Composition Language toolchain.")


@app.command()
def compile(file: str = typer.Argument(..., help="Path to .pcl file")) -> None:
    """Compile a .pcl file and print the output."""
    raise NotImplementedError


@app.command()
def render(
    file: str = typer.Argument(..., help="Path to .pcl file"),
    var: list[str] = typer.Option([], "--var", help="Variable as key=value"),
) -> None:
    """Render a .pcl file with variables and print the output."""
    raise NotImplementedError


@app.command()
def check(file: str = typer.Argument(..., help="Path to .pcl file")) -> None:
    """Validate a .pcl file without producing output. Exits 1 on error."""
    raise NotImplementedError


@app.command()
def watch(file: str = typer.Argument(..., help="Path to .pcl file")) -> None:
    """Watch a .pcl file and recompile on change."""
    raise NotImplementedError
