"""PCL compiler — two-phase compilation model.

Phase A: compile(path) → CompiledTemplate (IR)
    Parses files, resolves imports, expands includes, strips comments/blocks.
    Produces a flat list of segments: str | VarRef | Conditional.

Phase B: render(compiled_or_path, variables) → str
    Walks the IR, substitutes variables, evaluates conditionals.
    Cheap — no file I/O, can be called many times with different variable sets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .errors import PCLError
from .datamodel.ast import (
    BlockDefNode,
    IfNode,
    IncludeNode,
    ParsedFile,
    RawNode,
    TextNode,
)
from .parser import parse_file
from .datamodel import (
    Segment,
    Conditional,
    VarRef,
    CompiledTemplate
)

# Matches ${var} or ${var | default}, and \${ (escaped)
_INTERP_RE = re.compile(r"(\\?\$\{([^}]+)\})")

# ---------------------------------------------------------------------------
# Namespace entry (internal)
# ---------------------------------------------------------------------------


@dataclass
class _Namespace:
    pf: ParsedFile
    blocks: dict[str, BlockDefNode]
    base_dir: Path


# ---------------------------------------------------------------------------
# Compiler — Phase A: AST → IR
# ---------------------------------------------------------------------------


class _Compiler:
    def __init__(self) -> None:
        self._file_cache: dict[str, ParsedFile] = {}

    def load(self, path: Path, load_stack: frozenset[str] = frozenset()) -> ParsedFile:
        """
        File loading + circular import detection
        """
        key = str(path.resolve())
        if key in load_stack:
            raise PCLError(f"Circular import detected: {path.name}")
        if key in self._file_cache:
            return self._file_cache[key]
        try:
            pf = parse_file(path)
        except FileNotFoundError:
            raise PCLError(f"File not found: {path}")
        self._file_cache[key] = pf
        new_stack = load_stack | {key}
        for imp in pf.imports:
            imp_path = (path.parent / imp.path).resolve()
            self.load(imp_path, new_stack)
        return pf

    # ------------------------------------------------------------------
    # Namespace + block helpers
    # ------------------------------------------------------------------

    def _build_ns_map(self, pf: ParsedFile, base_dir: Path) -> dict[str, _Namespace]:
        ns_map: dict[str, _Namespace] = {}
        for imp in pf.imports:
            imp_path = (base_dir / imp.path).resolve()
            imported_pf = self._file_cache[str(imp_path)]
            ns_map[imp.namespace] = _Namespace(
                pf=imported_pf,
                blocks=self._collect_blocks(imported_pf.body),
                base_dir=imp_path.parent,
            )
        return ns_map

    def _collect_blocks(self, nodes: list) -> dict[str, BlockDefNode]:
        return {n.name: n for n in nodes if isinstance(n, BlockDefNode)}

    # ------------------------------------------------------------------
    # AST → IR (flatten everything except variables and conditionals)
    # ------------------------------------------------------------------

    def compile_to_ir(self, pf: ParsedFile, base_dir: Path) -> list[Segment]:
        ns_map = self._build_ns_map(pf, base_dir)
        local_blocks = self._collect_blocks(pf.body)
        return self._flatten_nodes(
            pf.body, local_blocks, ns_map, base_dir, frozenset()
        )

    def _flatten_nodes(
        self,
        nodes: list,
        local_blocks: dict[str, BlockDefNode],
        ns_map: dict[str, _Namespace],
        base_dir: Path,
        include_stack: frozenset[str],
    ) -> list[Segment]:
        out: list[Segment] = []
        for node in nodes:
            out.extend(
                self._flatten_node(node, local_blocks, ns_map, base_dir, include_stack)
            )
        return out

    def _flatten_node(
        self,
        node,
        local_blocks: dict[str, BlockDefNode],
        ns_map: dict[str, _Namespace],
        base_dir: Path,
        include_stack: frozenset[str],
    ) -> list[Segment]:
        if isinstance(node, BlockDefNode):
            return []

        if isinstance(node, TextNode):
            segs = self._text_to_segments(node.text, node.line)
            segs.append("\n")
            return segs

        if isinstance(node, RawNode):
            return ["\n".join(node.lines)]

        if isinstance(node, IncludeNode):
            return self._flatten_include(
                node, local_blocks, ns_map, base_dir, include_stack
            )

        if isinstance(node, IfNode):
            body_segments = self._flatten_nodes(
                node.body, local_blocks, ns_map, base_dir, include_stack
            )
            return [
                Conditional(
                    variable=node.variable,
                    negated=node.negated,
                    body=body_segments,
                    line=node.line,
                )
            ]

        return []  # pragma: no cover

    # ------------------------------------------------------------------
    # Text → segments (split on variable references)
    # ------------------------------------------------------------------

    def _text_to_segments(self, text: str, lineno: int) -> list[Segment]:
        segments: list[Segment] = []
        last_end = 0

        for m in _INTERP_RE.finditer(text):
            full = m.group(1)
            start = m.start(1)

            # Literal text before this match
            if start > last_end:
                segments.append(text[last_end:start])

            if full.startswith("\\"):
                # \${ → literal ${...}
                segments.append("${" + m.group(2) + "}")
            else:
                inner = m.group(2)
                if "|" in inner:
                    var_name, default = inner.split("|", 1)
                    var_name = var_name.strip()
                    default = default.strip()
                else:
                    var_name = inner.strip()
                    default = None
                segments.append(VarRef(name=var_name, default=default, line=lineno))

            last_end = m.end(1)

        # Trailing text
        if last_end < len(text):
            segments.append(text[last_end:])

        return segments

    # ------------------------------------------------------------------
    # @include → IR
    # ------------------------------------------------------------------

    def _flatten_include(
        self,
        node: IncludeNode,
        local_blocks: dict[str, BlockDefNode],
        ns_map: dict[str, _Namespace],
        base_dir: Path,
        include_stack: frozenset[str],
    ) -> list[Segment]:
        ref = node.ref

        if "." in ref:
            ns_name, block_name = ref.split(".", 1)
            if ns_name not in ns_map:
                raise PCLError(f"Unknown namespace {ns_name!r}", line=node.line)
            ns = ns_map[ns_name]
            if block_name not in ns.blocks:
                raise PCLError(
                    f"Block {block_name!r} not found in namespace {ns_name!r}",
                    line=node.line,
                )
            key = ref
            if key in include_stack:
                raise PCLError(f"Circular include: {key!r}", line=node.line)
            block = ns.blocks[block_name]
            ns_ns_map = self._build_ns_map(ns.pf, ns.base_dir)
            return self._flatten_nodes(
                block.body, ns.blocks, ns_ns_map, ns.base_dir,
                include_stack | {key},
            )

        if ref in local_blocks:
            if ref in include_stack:
                raise PCLError(f"Circular include: {ref!r}", line=node.line)
            block = local_blocks[ref]
            return self._flatten_nodes(
                block.body, local_blocks, ns_map, base_dir,
                include_stack | {ref},
            )

        if ref in ns_map:
            ns = ns_map[ref]
            ns_ns_map = self._build_ns_map(ns.pf, ns.base_dir)
            ns_local_blocks = self._collect_blocks(ns.pf.body)
            file_key = f"__file__{str(ns.base_dir)}"
            if file_key in include_stack:
                raise PCLError(f"Circular import: {ref!r}", line=node.line)
            return self._flatten_nodes(
                ns.pf.body, ns_local_blocks, ns_ns_map, ns.base_dir,
                include_stack | {file_key},
            )

        raise PCLError(f"Unknown block or namespace {ref!r}", line=node.line)


# ---------------------------------------------------------------------------
# Phase B: IR → string (render)
# ---------------------------------------------------------------------------


def _render_segments(segments: list[Segment], variables: dict) -> list[str]:
    """Walk IR segments and produce output lines."""
    parts: list[str] = []
    for seg in segments:
        if isinstance(seg, str):
            parts.append(seg)
        elif isinstance(seg, VarRef):
            if seg.name in variables:
                parts.append(str(variables[seg.name]))
            elif seg.default is not None:
                parts.append(seg.default)
            else:
                raise PCLError(
                    f"Undefined variable {seg.name!r} with no default",
                    line=seg.line,
                )
        elif isinstance(seg, Conditional):
            value = bool(variables.get(seg.variable, False))
            active = (not value) if seg.negated else value
            if active:
                parts.extend(_render_segments(seg.body, variables))
    return parts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compile(path: str | Path) -> CompiledTemplate:
    """Parse and compile a .pcl file into an IR. No variables needed.

    Returns a CompiledTemplate with .metadata and .segments.
    Call render() on it with variables to get the final string.
    """
    p = Path(path).resolve()
    compiler = _Compiler()
    pf = compiler.load(p)
    metadata = pf.frontmatter.data if pf.frontmatter else {}
    segments = compiler.compile_to_ir(pf, base_dir=p.parent)
    return CompiledTemplate(metadata=metadata, segments=segments)


def render(
    source: str | Path | CompiledTemplate,
    *,
    variables: dict | None = None,
) -> str:
    """Render a .pcl file or CompiledTemplate to a string.

    Accepts either a file path (compiles internally) or a pre-compiled template.
    """
    if isinstance(source, CompiledTemplate):
        template = source
    else:
        template = compile(source)

    parts = _render_segments(template.segments, variables or {})
    text = "".join(parts)

    # Ensure trailing newline for non-empty output
    if text and not text.endswith("\n"):
        text += "\n"
    return text
