"""PCL line-by-line recursive-descent parser → AST."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

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
# Regex patterns
# ---------------------------------------------------------------------------

_IMPORT_RE = re.compile(r"^@import\s+(\S+)(?:\s+as\s+(\S+))?\s*$")
_BLOCK_DEF_RE = re.compile(r"^block\s+(\w[\w-]*)\s*:\s*$")
_INCLUDE_RE = re.compile(r"^@include\s+(\S+)\s*$")
_IF_RE = re.compile(r"^@(if not|if)\s+(\w+)\s*:\s*$")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class _Parser:
    def __init__(self, source: str, filename: str) -> None:
        self._lines = source.splitlines()
        self._pos = 0
        self._filename = filename

    # ------------------------------------------------------------------
    # Primitives
    # ------------------------------------------------------------------

    @property
    def _lineno(self) -> int:
        return self._pos + 1

    def _peek(self) -> str | None:
        if self._pos < len(self._lines):
            return self._lines[self._pos]
        return None

    def _advance(self) -> str:
        line = self._lines[self._pos]
        self._pos += 1
        return line

    def _at_end(self) -> bool:
        return self._pos >= len(self._lines)

    def _error(self, msg: str, line: int | None = None) -> PCLError:
        return PCLError(msg, line=line or self._lineno, file=self._filename)

    # ------------------------------------------------------------------
    # Top-level
    # ------------------------------------------------------------------

    def parse(self) -> ParsedFile:
        frontmatter = self._parse_frontmatter()
        imports = self._parse_imports()
        body = self._parse_body(indent=0)
        return ParsedFile(
            frontmatter=frontmatter,
            imports=imports,
            body=body,
            filename=self._filename,
        )

    # ------------------------------------------------------------------
    # Frontmatter
    # ------------------------------------------------------------------

    def _parse_frontmatter(self) -> FrontmatterNode | None:
        if self._peek() != "---":
            return None
        start = self._lineno
        self._advance()  # consume opening ---
        yaml_lines: list[str] = []
        while not self._at_end():
            raw = self._peek()
            if raw == "---":
                self._advance()
                try:
                    data = yaml.safe_load("\n".join(yaml_lines)) or {}
                except yaml.YAMLError as exc:
                    raise self._error(f"Invalid frontmatter YAML: {exc}", line=start)
                return FrontmatterNode(data=data, line=start)
            yaml_lines.append(self._advance())
        raise self._error("Frontmatter opened with --- but never closed", line=start)

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def _parse_imports(self) -> list[ImportNode]:
        imports: list[ImportNode] = []
        while not self._at_end():
            raw = self._peek()
            assert raw is not None
            stripped = raw.strip()
            # skip blank lines and comments before body
            if stripped == "" or stripped.startswith("#"):
                self._advance()
                continue
            if not stripped.startswith("@import"):
                break
            lineno = self._lineno
            self._advance()
            m = _IMPORT_RE.match(stripped)
            if not m:
                raise self._error(f"Invalid @import syntax: {raw!r}", line=lineno)
            path = m.group(1)
            ns = m.group(2) if m.group(2) else Path(path).stem
            imports.append(ImportNode(path=path, namespace=ns, line=lineno))
        return imports

    # ------------------------------------------------------------------
    # Body
    # ------------------------------------------------------------------

    def _parse_body(self, indent: int) -> list:
        """Parse body nodes at the given indentation level.

        Stops when a non-blank line has fewer than *indent* leading spaces.
        """
        nodes: list = []
        prefix = " " * indent

        while not self._at_end():
            raw = self._peek()
            assert raw is not None

            # --- Blank line ---
            if raw.strip() == "":
                nodes.append(TextNode(text="", line=self._lineno))
                self._advance()
                continue

            # --- Indentation check (only when indent > 0) ---
            if indent > 0:
                leading = len(raw) - len(raw.lstrip(" "))
                if leading < indent:
                    break  # dedented past our level — end of this body

            lineno = self._lineno

            # Strip indent prefix to get the local content
            content = raw[indent:] if indent > 0 else raw

            # --- Comment ---
            content_stripped = content.lstrip()
            if content_stripped.startswith("#") and not content_stripped.startswith("#"):
                # unreachable branch kept as guard — handled below
                pass

            first_nonws = content_stripped[0] if content_stripped else ""

            if first_nonws == "#":
                self._advance()
                continue

            # Handle escape sequences at directive-check level
            if content_stripped.startswith("\\@"):
                self._advance()
                nodes.append(TextNode(text=content_stripped[1:], line=lineno))
                continue

            if content_stripped.startswith("\\#"):
                self._advance()
                nodes.append(TextNode(text=content_stripped[1:], line=lineno))
                continue

            # --- @import in body = error ---
            if content_stripped.startswith("@import"):
                raise self._error("@import must appear before the body", line=lineno)

            # --- Block definition ---
            m = _BLOCK_DEF_RE.match(content_stripped)
            if m:
                if indent > 0:
                    raise self._error(
                        "Block definitions cannot be nested", line=lineno
                    )
                self._advance()
                block_body = self._parse_body(indent=4)
                nodes.append(
                    BlockDefNode(name=m.group(1), body=block_body, line=lineno)
                )
                continue

            # --- @include ---
            m = _INCLUDE_RE.match(content_stripped)
            if m:
                self._advance()
                nodes.append(IncludeNode(ref=m.group(1), line=lineno))
                continue

            # --- @if / @if not ---
            m = _IF_RE.match(content_stripped)
            if m:
                negated = m.group(1) == "if not"
                variable = m.group(2)
                self._advance()
                if_body = self._parse_body(indent=indent + 4)
                nodes.append(
                    IfNode(
                        variable=variable,
                        negated=negated,
                        body=if_body,
                        line=lineno,
                    )
                )
                continue

            # --- @raw ---
            if content_stripped == "@raw":
                self._advance()
                raw_lines: list[str] = []
                found_end = False
                while not self._at_end():
                    inner = self._peek()
                    assert inner is not None
                    if inner.strip() == "@end":
                        self._advance()
                        found_end = True
                        break
                    raw_lines.append(self._advance())
                if not found_end:
                    raise self._error("@raw block not closed with @end", line=lineno)
                nodes.append(RawNode(lines=raw_lines, line=lineno))
                continue

            # --- Unknown directive ---
            if content_stripped.startswith("@"):
                directive = content_stripped.split()[0]
                raise self._error(f"Unknown directive: {directive!r}", line=lineno)

            # --- Plain text ---
            self._advance()
            nodes.append(TextNode(text=content, line=lineno))

        return nodes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse(source: str, filename: str = "<string>") -> ParsedFile:
    """Parse PCL source text and return a ParsedFile AST."""
    return _Parser(source, filename).parse()


def parse_file(path: str | Path) -> ParsedFile:
    """Read and parse a .pcl file from disk."""
    p = Path(path)
    source = p.read_text(encoding="utf-8")
    return _Parser(source, str(p)).parse()
