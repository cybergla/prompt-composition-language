"""PCL compiler — walks the AST and produces compiled output."""
# Stub — implementation comes in Phase 4.

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .errors import PCLError


@dataclass
class Template:
    """Result of compile(). Variables are not yet resolved."""

    metadata: dict
    _ast: object  # ParsedFile
    _path: Path


def compile(path: str | Path, *, variables: dict | None = None) -> Template:
    """Parse and compile a .pcl file. Variables remain unresolved."""
    raise NotImplementedError


def render(path: str | Path, *, variables: dict | None = None) -> str:
    """Compile and render a .pcl file with the given variables."""
    raise NotImplementedError
