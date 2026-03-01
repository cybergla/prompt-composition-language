"""Compiler tests — two-phase compilation model.

Round 1: basic text passthrough, metadata, comment/block stripping.
Round 2: block definitions + @include (same file).
Round 3: cross-file @import + @include namespace.
Round 4: variable interpolation and defaults.
Round 5: @if / @if not conditionals.
Round 6: @raw passthrough.
Round 7: error cases.
Round 8: IR structure (compile produces correct segment types).
Round 9: compile-once, render-many (reuse CompiledTemplate).
"""

import pytest
from pathlib import Path

from pcl.compiler import (
    compile as pcl_compile,
    render as pcl_render,
    CompiledTemplate,
    VarRef,
    Conditional,
)
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

    def test_compile_returns_compiled_template(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "---\nversion: 2\n---\nHi\n")
        t = pcl_compile(f)
        assert isinstance(t, CompiledTemplate)

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
            pcl_compile(f)

    def test_circular_include_raises(self, tmp_path):
        src = "@block a:\n    @include a\n\n@include a\n"
        f = make_file(tmp_path, "a.pcl", src)
        with pytest.raises(PCLError, match="[Cc]ircular"):
            pcl_compile(f)


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
        result = pcl_render(f, variables={})
        assert "${undefined_var}" in result

    def test_raw_not_comment_stripped(self, tmp_path):
        src = "@raw\n# this is not stripped\n@end\n"
        f = make_file(tmp_path, "a.pcl", src)
        result = pcl_render(f, variables={})
        assert "# this is not stripped" in result


# ===========================================================================
# Round 8 — IR structure (compile produces correct segment types)
# ===========================================================================


class TestIRStructure:
    def test_plain_text_produces_str_segments(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Hello world\n")
        t = pcl_compile(f)
        assert all(isinstance(s, str) for s in t.segments)

    def test_variable_produces_varref_segment(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Hello ${name}\n")
        t = pcl_compile(f)
        varrefs = [s for s in t.segments if isinstance(s, VarRef)]
        assert len(varrefs) == 1
        assert varrefs[0].name == "name"
        assert varrefs[0].default is None

    def test_variable_with_default_in_varref(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "${name | world}\n")
        t = pcl_compile(f)
        varrefs = [s for s in t.segments if isinstance(s, VarRef)]
        assert varrefs[0].name == "name"
        assert varrefs[0].default == "world"

    def test_conditional_produces_conditional_segment(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "@if flag:\n    Content\n")
        t = pcl_compile(f)
        conds = [s for s in t.segments if isinstance(s, Conditional)]
        assert len(conds) == 1
        assert conds[0].variable == "flag"
        assert conds[0].negated is False

    def test_conditional_not_produces_negated(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "@if not flag:\n    Content\n")
        t = pcl_compile(f)
        conds = [s for s in t.segments if isinstance(s, Conditional)]
        assert conds[0].negated is True

    def test_include_expanded_in_ir(self, tmp_path):
        src = "@block greeting:\n    Hello\n\n@include greeting\n"
        f = make_file(tmp_path, "a.pcl", src)
        t = pcl_compile(f)
        # IR should contain the expanded "Hello" text, not an include reference
        text_segments = [s for s in t.segments if isinstance(s, str)]
        assert any("Hello" in s for s in text_segments)

    def test_raw_block_produces_str_segment(self, tmp_path):
        src = "@raw\n${literal}\n@end\n"
        f = make_file(tmp_path, "a.pcl", src)
        t = pcl_compile(f)
        text_segments = [s for s in t.segments if isinstance(s, str)]
        assert any("${literal}" in s for s in text_segments)
        # Should NOT produce VarRef for raw content
        varrefs = [s for s in t.segments if isinstance(s, VarRef)]
        assert len(varrefs) == 0

    def test_escaped_dollar_produces_str_not_varref(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "\\${amount}\n")
        t = pcl_compile(f)
        varrefs = [s for s in t.segments if isinstance(s, VarRef)]
        assert len(varrefs) == 0
        text = "".join(s for s in t.segments if isinstance(s, str))
        assert "${amount}" in text


# ===========================================================================
# Round 9 — Compile-once, render-many
# ===========================================================================


class TestCompileOnceRenderMany:
    def test_same_template_different_variables(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Hello ${name}\n")
        t = pcl_compile(f)
        assert pcl_render(t, variables={"name": "Alice"}) == "Hello Alice\n"
        assert pcl_render(t, variables={"name": "Bob"}) == "Hello Bob\n"

    def test_conditional_renders_differently(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "@if premium:\n    Premium\n")
        t = pcl_compile(f)
        assert "Premium" in pcl_render(t, variables={"premium": True})
        assert "Premium" not in pcl_render(t, variables={"premium": False})

    def test_render_path_same_as_compile_then_render(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Hello ${name}\n")
        vars = {"name": "Alice"}
        direct = pcl_render(f, variables=vars)
        compiled = pcl_compile(f)
        via_template = pcl_render(compiled, variables=vars)
        assert direct == via_template
