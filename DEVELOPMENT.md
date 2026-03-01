# Development Guide

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (package manager)

## Setup

```bash
cd src/pcl

# Create virtual environment and activate it
uv venv && source .venv/bin/activate

# Install the package in editable mode with dev dependencies
uv pip install -e ".[dev]"
```

## Running Tests

```bash
uv run pytest tests/ -q
```

With coverage:

```bash
uv run pytest tests/ --cov=pcl --cov-report=term-missing
```

## Using the CLI

After installation, the `pcl` command is available:

```bash
pcl check examples/agent.pcl
pcl compile examples/agent.pcl
pcl render examples/agent.pcl --var date=2025-01-01 --var query="hello" --var premium=true
pcl watch examples/agent.pcl --var date=2025-01-01
```

## Building a Distribution

```bash
uv run python -m build
```

This produces a wheel and sdist in `dist/`.

## Project Layout

```
src/pcl/
  src/pcl/          # package source
    __init__.py     # public API (compile, render)
    parser.py       # line-by-line recursive descent parser
    compiler.py     # two-phase IR compiler
    cli.py          # Typer CLI
    errors.py       # PCLError with line/file context
  tests/            # pytest test suite
  examples/         # sample .pcl files
  pyproject.toml    # build config (hatchling)
```
