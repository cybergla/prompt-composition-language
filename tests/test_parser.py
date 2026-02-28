"""Parser tests — written spec-first (TDD).

Round 1: frontmatter, comments, text nodes, imports.
Round 2: @block definitions, @include.
Round 3: @if / @if not, @raw / @end, escape sequences, error cases.
"""

import pytest

from pcl.parser import (
    BlockDefNode,
    FrontmatterNode,
    IfNode,
    ImportNode,
    IncludeNode,
    ParsedFile,
    RawNode,
    TextNode,
    parse,
)
from pcl.errors import PCLError


# ===========================================================================
# Helpers
# ===========================================================================


def body_types(pf: ParsedFile) -> list[type]:
    return [type(n) for n in pf.body]


# ===========================================================================
# Round 1 — Frontmatter, comments, text, imports
# ===========================================================================


class TestFrontmatter:
    def test_no_frontmatter(self):
        pf = parse("Hello world\n")
        assert pf.frontmatter is None

    def test_frontmatter_parsed(self):
        src = "---\nversion: 1.0\ndescription: test\n---\nBody text\n"
        pf = parse(src)
        assert pf.frontmatter is not None
        assert pf.frontmatter.data == {"version": 1.0, "description": "test"}

    def test_frontmatter_empty(self):
        src = "---\n---\nBody\n"
        pf = parse(src)
        assert pf.frontmatter is not None
        assert pf.frontmatter.data == {}

    def test_frontmatter_arbitrary_keys(self):
        src = "---\nmodel: gpt-4\nauthor: alice\n---\n"
        pf = parse(src)
        assert pf.frontmatter.data["model"] == "gpt-4"
        assert pf.frontmatter.data["author"] == "alice"

    def test_frontmatter_unclosed_raises(self):
        src = "---\nversion: 1.0\n"
        with pytest.raises(PCLError, match="never closed"):
            parse(src)

    def test_frontmatter_line_number(self):
        src = "---\nversion: 1.0\n---\n"
        pf = parse(src)
        assert pf.frontmatter.line == 1

    def test_frontmatter_tolerates_leading_whitespace_on_delimiters(self):
        src = " ---\nversion: 1.0\n ---\nBody\n"
        pf = parse(src)
        assert pf.frontmatter is not None
        assert pf.frontmatter.data["version"] == 1.0


class TestComments:
    def test_comment_line_stripped(self):
        src = "# this is a comment\nHello\n"
        pf = parse(src)
        assert TextNode("Hello", 2) in pf.body
        assert not any(isinstance(n, TextNode) and "#" in n.text for n in pf.body)

    def test_comment_only_file(self):
        src = "# one\n# two\n"
        pf = parse(src)
        assert pf.body == []

    def test_mid_line_hash_is_literal(self):
        src = "Hello # world\n"
        pf = parse(src)
        assert pf.body == [TextNode("Hello # world", 1)]

    def test_indented_comment_stripped(self):
        src = "@block foo:\n    # comment inside block\n    Real line\n"
        pf = parse(src)
        block = pf.body[0]
        assert isinstance(block, BlockDefNode)
        assert all(
            not (isinstance(n, TextNode) and n.text.strip().startswith("#"))
            for n in block.body
        )


class TestTextNodes:
    def test_single_text_line(self):
        pf = parse("Hello world\n")
        assert pf.body == [TextNode("Hello world", 1)]

    def test_multiple_text_lines(self):
        pf = parse("Line one\nLine two\n")
        assert pf.body == [TextNode("Line one", 1), TextNode("Line two", 2)]

    def test_blank_lines_preserved(self):
        pf = parse("Line one\n\nLine two\n")
        assert len(pf.body) == 3
        assert pf.body[1] == TextNode("", 2)

    def test_text_after_frontmatter(self):
        src = "---\nversion: 1\n---\nBody line\n"
        pf = parse(src)
        assert pf.body == [TextNode("Body line", 4)]

    def test_line_numbers_correct(self):
        src = "# comment\nLine A\nLine B\n"
        pf = parse(src)
        assert pf.body[0].line == 2
        assert pf.body[1].line == 3


class TestImports:
    def test_simple_import(self):
        src = "@import ./persona.pcl\nBody\n"
        pf = parse(src)
        assert len(pf.imports) == 1
        imp = pf.imports[0]
        assert imp.path == "./persona.pcl"
        assert imp.namespace == "persona"
        assert imp.line == 1

    def test_import_with_as(self):
        src = "@import ./tools.pcl as tools\nBody\n"
        pf = parse(src)
        imp = pf.imports[0]
        assert imp.path == "./tools.pcl"
        assert imp.namespace == "tools"

    def test_multiple_imports(self):
        src = "@import ./a.pcl\n@import ./b.pcl as bb\nBody\n"
        pf = parse(src)
        assert len(pf.imports) == 2
        assert pf.imports[0].namespace == "a"
        assert pf.imports[1].namespace == "bb"

    def test_import_after_body_raises(self):
        src = "Body line\n@import ./foo.pcl\n"
        with pytest.raises(PCLError, match="before the body"):
            parse(src)

    def test_import_namespace_stem(self):
        src = "@import ./my-file.pcl\n"
        pf = parse(src)
        assert pf.imports[0].namespace == "my-file"

    def test_no_imports(self):
        pf = parse("Hello\n")
        assert pf.imports == []

    def test_imports_not_in_body(self):
        src = "@import ./foo.pcl\nHello\n"
        pf = parse(src)
        assert not any(isinstance(n, ImportNode) for n in pf.body)


# ===========================================================================
# Round 2 — @block definitions, @include
# ===========================================================================


class TestBlockDefinitions:
    def test_simple_block(self):
        src = "@block greeting:\n    Hello there.\n"
        pf = parse(src)
        assert len(pf.body) == 1
        block = pf.body[0]
        assert isinstance(block, BlockDefNode)
        assert block.name == "greeting"
        assert block.body == [TextNode("Hello there.", 2)]

    def test_block_multi_line_body(self):
        src = "@block intro:\n    Line one.\n    Line two.\n"
        pf = parse(src)
        block = pf.body[0]
        assert len(block.body) == 2

    def test_block_body_stripped_of_indent(self):
        src = "@block foo:\n    Content here\n"
        pf = parse(src)
        block = pf.body[0]
        assert block.body[0].text == "Content here"

    def test_nested_block_definition_raises(self):
        src = "@block outer:\n    @block inner:\n        Text\n"
        with pytest.raises(PCLError, match="cannot be nested"):
            parse(src)

    def test_two_consecutive_blocks(self):
        src = "@block a:\n    A body\n\n@block b:\n    B body\n"
        pf = parse(src)
        names = [n.name for n in pf.body if isinstance(n, BlockDefNode)]
        assert names == ["a", "b"]

    def test_block_line_number(self):
        src = "# comment\n@block foo:\n    body\n"
        pf = parse(src)
        block = pf.body[0]
        assert block.line == 2


class TestIncludes:
    def test_simple_include(self):
        pf = parse("@include greeting\n")
        assert pf.body == [IncludeNode("greeting", 1)]

    def test_namespaced_include(self):
        pf = parse("@include tools.search\n")
        assert pf.body == [IncludeNode("tools.search", 1)]

    def test_include_entire_namespace(self):
        pf = parse("@include persona\n")
        assert pf.body == [IncludeNode("persona", 1)]

    def test_include_inside_block(self):
        src = "@block composed:\n    @include base\n"
        pf = parse(src)
        block = pf.body[0]
        assert isinstance(block, BlockDefNode)
        assert block.body == [IncludeNode("base", 2)]

    def test_include_line_number(self):
        src = "Text\n@include foo\n"
        pf = parse(src)
        inc = pf.body[1]
        assert isinstance(inc, IncludeNode)
        assert inc.line == 2


# ===========================================================================
# Round 3 — Conditionals, @raw/@end, escaping, error cases
# ===========================================================================


class TestConditionals:
    def test_if_basic(self):
        src = "@if premium:\n    Upgrade message\n"
        pf = parse(src)
        node = pf.body[0]
        assert isinstance(node, IfNode)
        assert node.variable == "premium"
        assert node.negated is False
        assert node.body == [TextNode("Upgrade message", 2)]

    def test_if_not(self):
        src = "@if not premium:\n    Basic message\n"
        pf = parse(src)
        node = pf.body[0]
        assert isinstance(node, IfNode)
        assert node.negated is True
        assert node.variable == "premium"

    def test_nested_conditionals(self):
        src = "@if a:\n    @if b:\n        Deep text\n"
        pf = parse(src)
        outer = pf.body[0]
        assert isinstance(outer, IfNode)
        inner = outer.body[0]
        assert isinstance(inner, IfNode)
        assert inner.body == [TextNode("Deep text", 3)]

    def test_if_inside_block(self):
        src = "@block foo:\n    @if x:\n        Conditional\n"
        pf = parse(src)
        block = pf.body[0]
        assert isinstance(block, BlockDefNode)
        if_node = block.body[0]
        assert isinstance(if_node, IfNode)

    def test_if_line_number(self):
        src = "Text\n@if flag:\n    Body\n"
        pf = parse(src)
        if_node = pf.body[1]
        assert isinstance(if_node, IfNode)
        assert if_node.line == 2


class TestRawBlocks:
    def test_raw_basic(self):
        src = "@raw\n    {\"key\": \"${not_interpolated}\"}\n@end\n"
        pf = parse(src)
        node = pf.body[0]
        assert isinstance(node, RawNode)
        assert node.lines == ['    {"key": "${not_interpolated}"}']

    def test_raw_multi_line(self):
        src = "@raw\nline one\nline two\n@end\n"
        pf = parse(src)
        node = pf.body[0]
        assert node.lines == ["line one", "line two"]

    def test_raw_empty(self):
        src = "@raw\n@end\n"
        pf = parse(src)
        node = pf.body[0]
        assert isinstance(node, RawNode)
        assert node.lines == []

    def test_raw_unclosed_raises(self):
        src = "@raw\nsome content\n"
        with pytest.raises(PCLError, match="not closed"):
            parse(src)

    def test_raw_line_number(self):
        src = "Text\n@raw\nstuff\n@end\n"
        pf = parse(src)
        raw = pf.body[1]
        assert isinstance(raw, RawNode)
        assert raw.line == 2


class TestEscaping:
    def test_escaped_at_sign(self):
        src = "\\@import is literal\n"
        pf = parse(src)
        assert isinstance(pf.body[0], TextNode)
        assert pf.body[0].text == "@import is literal"

    def test_escaped_at_block(self):
        src = "\\@block foo: is literal\n"
        pf = parse(src)
        assert isinstance(pf.body[0], TextNode)
        assert pf.body[0].text == "@block foo: is literal"

    def test_escaped_hash(self):
        src = "\\# not a comment\n"
        pf = parse(src)
        assert isinstance(pf.body[0], TextNode)
        assert pf.body[0].text == "# not a comment"

    def test_escaped_dollar_brace_preserved(self):
        # \${ is kept literally in the TextNode — interpolation handles it at render time
        src = "Price: \\${amount}\n"
        pf = parse(src)
        assert pf.body[0].text == "Price: \\${amount}"


class TestErrorCases:
    def test_unknown_directive_raises(self):
        with pytest.raises(PCLError, match="Unknown directive"):
            parse("@unknown foo\n")

    def test_import_malformed_raises(self):
        with pytest.raises(PCLError):
            parse("@import\n")

    def test_end_without_raw_raises(self):
        with pytest.raises(PCLError, match="Unknown directive"):
            parse("@end\n")
