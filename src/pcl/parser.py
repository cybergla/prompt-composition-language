"""PCL line-by-line parser → AST."""
# Stub — implementation comes in Phase 2 / 3.

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .errors import PCLError


# ---------------------------------------------------------------------------
# AST node types
# ---------------------------------------------------------------------------


@dataclass
class FrontmatterNode:
    data: dict
    line: int = 0


@dataclass
class ImportNode:
    path: str
    namespace: str
    line: int


@dataclass
class BlockDefNode:
    name: str
    body: list  # list[BodyNode]
    line: int


@dataclass
class IncludeNode:
    ref: str
    line: int


@dataclass
class IfNode:
    variable: str
    negated: bool
    body: list  # list[BodyNode]
    line: int


@dataclass
class RawNode:
    lines: list[str]
    line: int


@dataclass
class TextNode:
    text: str
    line: int


@dataclass
class ParsedFile:
    frontmatter: FrontmatterNode | None
    imports: list[ImportNode]
    body: list  # list[BodyNode]
    filename: str = "<string>"


# ---------------------------------------------------------------------------
# Public API (stubs — raise NotImplementedError until implemented)
# ---------------------------------------------------------------------------


def parse(source: str, filename: str = "<string>") -> ParsedFile:
    """Parse PCL source text and return a ParsedFile AST."""
    raise NotImplementedError


def parse_file(path: str | Path) -> ParsedFile:
    """Read and parse a PCL file."""
    raise NotImplementedError
