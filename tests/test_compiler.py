"""Compiler tests — written spec-first (TDD).

Round 1: basic text passthrough, comment/block-def stripping.
Round 2: block definitions + @include (same file).
Round 3: cross-file @import + @include namespace.
Round 4: variable interpolation and defaults.
Round 5: @if / @if not conditionals.
Round 6: @raw passthrough.
Round 7: error cases (circular include, circular import, undefined var).
"""

import pytest
from pathlib import Path

from pcl.compiler import compile as pcl_compile, render as pcl_render, Template
from pcl.errors import PCLError


# ===========================================================================
# Helpers
# ===========================================================================


def make_file(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ===========================================================================
# Round 1 — Text passthrough, metadata, comment/block stripping
# ===========================================================================


class TestBasicOutput:
    def test_plain_text_passthrough(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Hello world\n")
        result = pcl_render(f)
        assert result == "Hello world\n"

    def test_multiline_text(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Line one\nLine two\n")
        result = pcl_render(f)
        assert result == "Line one\nLine two\n"

    def test_comments_stripped(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "# comment\nHello\n")
        result = pcl_render(f)
        assert result == "Hello\n"
        assert "#" not in result

    def test_blank_lines_preserved(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Line one\n\nLine two\n")
        result = pcl_render(f)
        assert result == "Line one\n\nLine two\n"

    def test_block_definition_not_in_output(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "@block foo:\n    body text\n")
        result = pcl_render(f)
        assert result == ""

    def test_frontmatter_not_in_output(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "---\nversion: 1\n---\nHello\n")
        result = pcl_render(f)
        assert result == "Hello\n"
        assert "---" not in result

    def test_compile_returns_template(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "---\nversion: 2\n---\nHi\n")
        t = pcl_compile(f)
        assert isinstance(t, Template)

    def test_metadata_from_frontmatter(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "---\nversion: 1.2\ndescription: test\n---\n")
        t = pcl_compile(f)
        assert t.metadata["version"] == 1.2
        assert t.metadata["description"] == "test"

    def test_metadata_empty_when_no_frontmatter(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Hello\n")
        t = pcl_compile(f)
        assert t.metadata == {}


# ===========================================================================
# Round 2 — Block definitions + @include (same file)
# ===========================================================================


class TestBlocksAndIncludes:
    def test_include_emits_block_body(self, tmp_path):
        src = "@block greeting:\n    Hello there.\n\n@include greeting\n"
        f = make_file(tmp_path, "a.pcl", src)
        result = pcl_render(f)
        assert "Hello there." in result

    def test_block_definition_not_duplicated(self, tmp_path):
        src = "@block greeting:\n    Hello there.\n\n@include greeting\n"
        f = make_file(tmp_path, "a.pcl", src)
        result = pcl_render(f)
        # only one occurrence from the include, not two
        assert result.count("Hello there.") == 1

    def test_include_respects_position(self, tmp_path):
        src = "Before\n\n@block note:\n    [note]\n\nAfter\n\n@include note\n"
        f = make_file(tmp_path, "a.pcl", src)
        result = pcl_render(f)
        lines = [l for l in result.splitlines() if l.strip()]
        assert lines == ["Before", "After", "[note]"]

    def test_block_composed_of_includes(self, tmp_path):
        src = (
            "@block a:\n    Part A\n\n"
            "@block b:\n    @include a\n\n"
            "@include b\n"
        )
        f = make_file(tmp_path, "a.pcl", src)
        result = pcl_render(f)
        assert "Part A" in result

    def test_include_unknown_block_raises(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "@include nonexistent\n")
        with pytest.raises(PCLError, match="nonexistent"):
            pcl_render(f)

    def test_circular_include_raises(self, tmp_path):
        src = "@block a:\n    @include a\n\n@include a\n"
        f = make_file(tmp_path, "a.pcl", src)
        with pytest.raises(PCLError, match="[Cc]ircular"):
            pcl_render(f)


# ===========================================================================
# Round 3 — Cross-file @import + @include namespace
# ===========================================================================


class TestCrossFileImports:
    def test_include_entire_imported_file(self, tmp_path):
        make_file(tmp_path, "fragment.pcl", "Fragment body\n")
        main = make_file(tmp_path, "main.pcl", "@import ./fragment.pcl\n@include fragment\n")
        result = pcl_render(main)
        assert "Fragment body" in result

    def test_include_named_block_from_import(self, tmp_path):
        make_file(tmp_path, "lib.pcl", "@block greet:\n    Hi from lib\n")
        main = make_file(tmp_path, "main.pcl", "@import ./lib.pcl\n@include lib.greet\n")
        result = pcl_render(main)
        assert "Hi from lib" in result

    def test_import_as_namespace(self, tmp_path):
        make_file(tmp_path, "lib.pcl", "@block greet:\n    Hi from lib\n")
        main = make_file(tmp_path, "main.pcl", "@import ./lib.pcl as tools\n@include tools.greet\n")
        result = pcl_render(main)
        assert "Hi from lib" in result

    def test_import_missing_file_raises(self, tmp_path):
        main = make_file(tmp_path, "main.pcl", "@import ./missing.pcl\n@include missing\n")
        with pytest.raises((PCLError, FileNotFoundError)):
            pcl_render(main)

    def test_circular_import_raises(self, tmp_path):
        a = make_file(tmp_path, "a.pcl", "@import ./b.pcl\n@include b\n")
        make_file(tmp_path, "b.pcl", "@import ./a.pcl\n@include a\n")
        with pytest.raises(PCLError, match="[Cc]ircular"):
            pcl_render(a)


# ===========================================================================
# Round 4 — Variable interpolation
# ===========================================================================


class TestVariableInterpolation:
    def test_simple_variable(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Hello ${name}\n")
        result = pcl_render(f, variables={"name": "Alice"})
        assert result == "Hello Alice\n"

    def test_variable_with_default(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Hello ${name | stranger}\n")
        result = pcl_render(f, variables={})
        assert result == "Hello stranger\n"

    def test_variable_overrides_default(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Hello ${name | stranger}\n")
        result = pcl_render(f, variables={"name": "Bob"})
        assert result == "Hello Bob\n"

    def test_undefined_variable_no_default_raises(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Hello ${name}\n")
        with pytest.raises(PCLError, match="name"):
            pcl_render(f, variables={})

    def test_multiple_variables_on_one_line(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "${greeting}, ${name}!\n")
        result = pcl_render(f, variables={"greeting": "Hi", "name": "World"})
        assert result == "Hi, World!\n"

    def test_escaped_dollar_brace_is_literal(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Price: \\${amount}\n")
        result = pcl_render(f, variables={})
        assert result == "Price: ${amount}\n"

    def test_variable_in_block(self, tmp_path):
        src = "@block notice:\n    Today is ${date}.\n\n@include notice\n"
        f = make_file(tmp_path, "a.pcl", src)
        result = pcl_render(f, variables={"date": "2026-02-28"})
        assert "Today is 2026-02-28." in result


# ===========================================================================
# Round 5 — Conditionals
# ===========================================================================


class TestConditionals:
    def test_if_true_includes_body(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "@if premium:\n    Premium content\n")
        result = pcl_render(f, variables={"premium": True})
        assert "Premium content" in result

    def test_if_false_excludes_body(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "@if premium:\n    Premium content\n")
        result = pcl_render(f, variables={"premium": False})
        assert "Premium content" not in result

    def test_if_not_false_includes_body(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "@if not premium:\n    Basic content\n")
        result = pcl_render(f, variables={"premium": False})
        assert "Basic content" in result

    def test_if_not_true_excludes_body(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "@if not premium:\n    Basic content\n")
        result = pcl_render(f, variables={"premium": True})
        assert "Basic content" not in result

    def test_nested_conditionals(self, tmp_path):
        src = "@if a:\n    @if b:\n        Deep\n"
        f = make_file(tmp_path, "a.pcl", src)
        assert "Deep" in pcl_render(f, variables={"a": True, "b": True})
        assert "Deep" not in pcl_render(f, variables={"a": True, "b": False})
        assert "Deep" not in pcl_render(f, variables={"a": False, "b": True})

    def test_conditional_variable_missing_treated_as_false(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "@if flag:\n    Content\n")
        result = pcl_render(f, variables={})
        assert "Content" not in result

    def test_conditional_in_block(self, tmp_path):
        src = (
            "@block section:\n"
            "    @if show:\n"
            "        Shown\n"
            "\n"
            "@include section\n"
        )
        f = make_file(tmp_path, "a.pcl", src)
        assert "Shown" in pcl_render(f, variables={"show": True})
        assert "Shown" not in pcl_render(f, variables={"show": False})


# ===========================================================================
# Round 6 — @raw passthrough
# ===========================================================================


class TestRawBlocks:
    def test_raw_content_passes_through(self, tmp_path):
        src = '@raw\n{"tool": "${name}", "args": {}}\n@end\n'
        f = make_file(tmp_path, "a.pcl", src)
        result = pcl_render(f, variables={})
        assert '{"tool": "${name}", "args": {}}' in result

    def test_raw_not_interpolated(self, tmp_path):
        src = "@raw\n${undefined_var}\n@end\n"
        f = make_file(tmp_path, "a.pcl", src)
        # should NOT raise even though variable is undefined
        result = pcl_render(f, variables={})
        assert "${undefined_var}" in result

    def test_raw_not_comment_stripped(self, tmp_path):
        src = "@raw\n# this is not stripped\n@end\n"
        f = make_file(tmp_path, "a.pcl", src)
        result = pcl_render(f, variables={})
        assert "# this is not stripped" in result
