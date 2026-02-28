"""PCL compiler — walks the AST and produces the output string."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .errors import PCLError
from .parser import (
    BlockDefNode,
    FrontmatterNode,
    IfNode,
    ImportNode,
    IncludeNode,
    ParsedFile,
    RawNode,
    TextNode,
    parse_file,
)

# Matches ${var} or ${var | default value}, and \${ (escaped)
_INTERP_RE = re.compile(r"\\?\$\{([^}]+)\}")


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------


@dataclass
class Template:
    """Result of compile(). Variables are not yet resolved."""

    metadata: dict
    _ast: ParsedFile
    _path: Path


# ---------------------------------------------------------------------------
# Namespace entry: everything needed to render an imported file
# ---------------------------------------------------------------------------


@dataclass
class _Namespace:
    pf: ParsedFile
    blocks: dict[str, BlockDefNode]
    base_dir: Path


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------


class _Compiler:
    def __init__(self) -> None:
        # resolved path → ParsedFile, shared across the whole compile run
        self._file_cache: dict[str, ParsedFile] = {}

    # ------------------------------------------------------------------
    # File loading (parse + cache; circular import detection at load time)
    # ------------------------------------------------------------------

    def load(self, path: Path, load_stack: frozenset[str] = frozenset()) -> ParsedFile:
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
        # Eagerly load all transitive imports to detect circles early
        new_stack = load_stack | {key}
        for imp in pf.imports:
            imp_path = (path.parent / imp.path).resolve()
            self.load(imp_path, new_stack)
        return pf

    # ------------------------------------------------------------------
    # Build namespace map for a file
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

    # ------------------------------------------------------------------
    # Block registry
    # ------------------------------------------------------------------

    def _collect_blocks(self, nodes: list) -> dict[str, BlockDefNode]:
        return {n.name: n for n in nodes if isinstance(n, BlockDefNode)}

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def render(self, pf: ParsedFile, variables: dict, base_dir: Path) -> str:
        ns_map = self._build_ns_map(pf, base_dir)
        local_blocks = self._collect_blocks(pf.body)
        lines = self._render_nodes(
            pf.body, variables, local_blocks, ns_map, base_dir, frozenset()
        )
        return "\n".join(lines) + ("\n" if lines else "")

    # ------------------------------------------------------------------
    # Node rendering
    # ------------------------------------------------------------------

    def _render_nodes(
        self,
        nodes: list,
        variables: dict,
        local_blocks: dict[str, BlockDefNode],
        ns_map: dict[str, _Namespace],
        base_dir: Path,
        include_stack: frozenset[str],
    ) -> list[str]:
        out: list[str] = []
        for node in nodes:
            out.extend(
                self._render_node(
                    node, variables, local_blocks, ns_map, base_dir, include_stack
                )
            )
        return out

    def _render_node(
        self,
        node,
        variables: dict,
        local_blocks: dict[str, BlockDefNode],
        ns_map: dict[str, _Namespace],
        base_dir: Path,
        include_stack: frozenset[str],
    ) -> list[str]:
        if isinstance(node, BlockDefNode):
            return []

        if isinstance(node, TextNode):
            return [self._interpolate(node.text, variables, node.line)]

        if isinstance(node, RawNode):
            return node.lines

        if isinstance(node, IncludeNode):
            return self._render_include(
                node, variables, local_blocks, ns_map, base_dir, include_stack
            )

        if isinstance(node, IfNode):
            return self._render_if(
                node, variables, local_blocks, ns_map, base_dir, include_stack
            )

        return []  # pragma: no cover

    # ------------------------------------------------------------------
    # @include
    # ------------------------------------------------------------------

    def _render_include(
        self,
        node: IncludeNode,
        variables: dict,
        local_blocks: dict[str, BlockDefNode],
        ns_map: dict[str, _Namespace],
        base_dir: Path,
        include_stack: frozenset[str],
    ) -> list[str]:
        ref = node.ref

        if "." in ref:
            # @include namespace.blockname
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
            return self._render_nodes(
                block.body,
                variables,
                ns.blocks,
                ns_ns_map,
                ns.base_dir,
                include_stack | {key},
            )

        if ref in local_blocks:
            # @include blockname (same file)
            if ref in include_stack:
                raise PCLError(f"Circular include: {ref!r}", line=node.line)
            block = local_blocks[ref]
            return self._render_nodes(
                block.body,
                variables,
                local_blocks,
                ns_map,
                base_dir,
                include_stack | {ref},
            )

        if ref in ns_map:
            # @include namespace (entire imported file body)
            ns = ns_map[ref]
            ns_ns_map = self._build_ns_map(ns.pf, ns.base_dir)
            ns_local_blocks = self._collect_blocks(ns.pf.body)
            # Use file key for render-level circular detection
            file_key = f"__file__{str(ns.base_dir)}"
            if file_key in include_stack:
                raise PCLError(f"Circular import: {ref!r}", line=node.line)
            return self._render_nodes(
                ns.pf.body,
                variables,
                ns_local_blocks,
                ns_ns_map,
                ns.base_dir,
                include_stack | {file_key},
            )

        raise PCLError(f"Unknown block or namespace {ref!r}", line=node.line)

    # ------------------------------------------------------------------
    # @if / @if not
    # ------------------------------------------------------------------

    def _render_if(
        self,
        node: IfNode,
        variables: dict,
        local_blocks: dict[str, BlockDefNode],
        ns_map: dict[str, _Namespace],
        base_dir: Path,
        include_stack: frozenset[str],
    ) -> list[str]:
        value = bool(variables.get(node.variable, False))
        active = (not value) if node.negated else value
        if not active:
            return []
        return self._render_nodes(
            node.body, variables, local_blocks, ns_map, base_dir, include_stack
        )

    # ------------------------------------------------------------------
    # Variable interpolation
    # ------------------------------------------------------------------

    def _interpolate(self, text: str, variables: dict, lineno: int) -> str:
        def replace(m: re.Match) -> str:
            full = m.group(0)
            if full.startswith("\\"):
                # \${ → emit literal ${...}
                return "${" + m.group(1) + "}"
            inner = m.group(1)
            if "|" in inner:
                var_name, default = inner.split("|", 1)
                var_name = var_name.strip()
                default = default.strip()
            else:
                var_name = inner.strip()
                default = None

            if var_name in variables:
                return str(variables[var_name])
            if default is not None:
                return default
            raise PCLError(
                f"Undefined variable {var_name!r} with no default",
                line=lineno,
            )

        return _INTERP_RE.sub(replace, text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compile(path: str | Path, *, variables: dict | None = None) -> Template:
    """Parse and compile a .pcl file. Variables remain unresolved."""
    p = Path(path).resolve()
    compiler = _Compiler()
    pf = compiler.load(p)
    metadata = pf.frontmatter.data if pf.frontmatter else {}
    return Template(metadata=metadata, _ast=pf, _path=p)


def render(path: str | Path, *, variables: dict | None = None) -> str:
    """Compile and render a .pcl file with the given variables."""
    p = Path(path).resolve()
    compiler = _Compiler()
    pf = compiler.load(p)
    return compiler.render(pf, variables or {}, base_dir=p.parent)
