"""CLI tests — written spec-first (TDD).

Uses typer.testing.CliRunner so no subprocess overhead.
"""

import pytest
import cbor2
from pathlib import Path
from typer.testing import CliRunner

from pcl.cli import app
from pcl.compiler import serialize as pcl_serialize, compile as pcl_compile

runner = CliRunner()


# ===========================================================================
# Helpers
# ===========================================================================


def make_file(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ===========================================================================
# pcl compile
# ===========================================================================


class TestCompileCommand:
    def test_prints_compiled_output(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Hello world\n")
        result = runner.invoke(app, ["compile", str(f)])
        assert result.exit_code == 0
        assert "Hello world" in result.output

    def test_strips_comments(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "# comment\nHello\n")
        result = runner.invoke(app, ["compile", str(f)])
        assert result.exit_code == 0
        assert "#" not in result.output
        assert "Hello" in result.output

    def test_strips_frontmatter(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "---\nversion: 1\n---\nHello\n")
        result = runner.invoke(app, ["compile", str(f)])
        assert result.exit_code == 0
        assert "---" not in result.output
        assert "Hello" in result.output

    def test_missing_file_exits_nonzero(self, tmp_path):
        result = runner.invoke(app, ["compile", str(tmp_path / "nope.pcl")])
        assert result.exit_code != 0

    def test_invalid_pcl_exits_nonzero(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "@unknown directive\n")
        result = runner.invoke(app, ["compile", str(f)])
        assert result.exit_code != 0


# ===========================================================================
# pcl render
# ===========================================================================


class TestRenderCommand:
    def test_render_with_variable(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Hello ${name}\n")
        result = runner.invoke(app, ["render", str(f), "--var", "name=Alice"])
        assert result.exit_code == 0
        assert "Hello Alice" in result.output

    def test_render_multiple_vars(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "${greeting}, ${name}!\n")
        result = runner.invoke(
            app, ["render", str(f), "--var", "greeting=Hi", "--var", "name=World"]
        )
        assert result.exit_code == 0
        assert "Hi, World!" in result.output

    def test_render_bool_var_true(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "@if flag:\n    Active\n")
        result = runner.invoke(app, ["render", str(f), "--var", "flag=true"])
        assert result.exit_code == 0
        assert "Active" in result.output

    def test_render_bool_var_false(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "@if flag:\n    Active\n")
        result = runner.invoke(app, ["render", str(f), "--var", "flag=false"])
        assert result.exit_code == 0
        assert "Active" not in result.output

    def test_render_undefined_var_exits_nonzero(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Hello ${name}\n")
        result = runner.invoke(app, ["render", str(f)])
        assert result.exit_code != 0

    def test_render_var_with_default_no_var_provided(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Hello ${name | stranger}\n")
        result = runner.invoke(app, ["render", str(f)])
        assert result.exit_code == 0
        assert "Hello stranger" in result.output


# ===========================================================================
# pcl check
# ===========================================================================


class TestCheckCommand:
    def test_valid_file_exits_zero(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Hello world\n")
        result = runner.invoke(app, ["check", str(f)])
        assert result.exit_code == 0

    def test_invalid_file_exits_one(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "@unknown directive\n")
        result = runner.invoke(app, ["check", str(f)])
        assert result.exit_code == 1

    def test_check_prints_error_message(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "@raw\nno end\n")
        result = runner.invoke(app, ["check", str(f)])
        assert result.exit_code == 1
        assert len(result.output.strip()) > 0

    def test_check_missing_file_exits_nonzero(self, tmp_path):
        result = runner.invoke(app, ["check", str(tmp_path / "nope.pcl")])
        assert result.exit_code != 0

    def test_valid_file_no_error_output(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Hello\n")
        result = runner.invoke(app, ["check", str(f)])
        assert result.exit_code == 0
        # stdout may show "OK" or be empty — just no error
        assert "Error" not in result.output


# ===========================================================================
# pcl compile -o (write .pclc)
# ===========================================================================


class TestCompileOutputFlag:
    def test_writes_pclc_file(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Hello world\n")
        out = tmp_path / "a.pclc"
        result = runner.invoke(app, ["compile", str(f), "-o", str(out)])
        assert result.exit_code == 0
        assert out.exists()

    def test_output_is_valid_cbor(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Hello world\n")
        out = tmp_path / "a.pclc"
        runner.invoke(app, ["compile", str(f), "-o", str(out)])
        data = cbor2.loads(out.read_bytes())
        assert isinstance(data, dict)
        assert data.get("pcl_version") == 1

    def test_metadata_round_trip(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "---\nauthor: Alice\n---\nHello\n")
        out = tmp_path / "a.pclc"
        runner.invoke(app, ["compile", str(f), "-o", str(out)])
        data = cbor2.loads(out.read_bytes())
        assert data["metadata"]["author"] == "Alice"

    def test_prints_confirmation_message(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Hello\n")
        out = tmp_path / "a.pclc"
        result = runner.invoke(app, ["compile", str(f), "-o", str(out)])
        assert result.exit_code == 0
        assert str(out) in result.output

    def test_no_flag_still_dumps_human_readable(self, tmp_path):
        f = make_file(tmp_path, "a.pcl", "Hello world\n")
        result = runner.invoke(app, ["compile", str(f)])
        assert result.exit_code == 0
        assert "Segments:" in result.output

    def test_missing_source_exits_nonzero(self, tmp_path):
        out = tmp_path / "a.pclc"
        result = runner.invoke(app, ["compile", str(tmp_path / "nope.pcl"), "-o", str(out)])
        assert result.exit_code != 0


# ===========================================================================
# pcl render <file.pclc>
# ===========================================================================


def _write_pclc(tmp_path: Path, name: str, pcl_content: str) -> Path:
    """Compile a .pcl string and write a .pclc file."""
    src = make_file(tmp_path, name + ".pcl", pcl_content)
    template = pcl_compile(src)
    out = tmp_path / (name + ".pclc")
    out.write_bytes(cbor2.dumps(pcl_serialize(template)))
    return out


class TestRenderFromPclc:
    def test_plain_text(self, tmp_path):
        pclc = _write_pclc(tmp_path, "a", "Hello world\n")
        result = runner.invoke(app, ["render", str(pclc)])
        assert result.exit_code == 0
        assert "Hello world" in result.output

    def test_with_variable(self, tmp_path):
        pclc = _write_pclc(tmp_path, "a", "Hello ${name}\n")
        result = runner.invoke(app, ["render", str(pclc), "--var", "name=Alice"])
        assert result.exit_code == 0
        assert "Hello Alice" in result.output

    def test_undefined_var_exits_nonzero(self, tmp_path):
        pclc = _write_pclc(tmp_path, "a", "Hello ${name}\n")
        result = runner.invoke(app, ["render", str(pclc)])
        assert result.exit_code != 0

    def test_conditional(self, tmp_path):
        pclc = _write_pclc(tmp_path, "a", "@if premium:\n    Premium content\n")
        result = runner.invoke(app, ["render", str(pclc), "--var", "premium=true"])
        assert result.exit_code == 0
        assert "Premium content" in result.output

    def test_missing_file_exits_nonzero(self, tmp_path):
        result = runner.invoke(app, ["render", str(tmp_path / "nope.pclc")])
        assert result.exit_code != 0

    def test_invalid_cbor_exits_nonzero(self, tmp_path):
        bad = tmp_path / "bad.pclc"
        bad.write_bytes(b"not cbor at all!!!")
        result = runner.invoke(app, ["render", str(bad)])
        assert result.exit_code != 0

    def test_round_trip_matches_pcl_render(self, tmp_path):
        content = "Hello ${name}\n"
        src = make_file(tmp_path, "a.pcl", content)
        pclc = _write_pclc(tmp_path, "b", content)
        pcl_result = runner.invoke(app, ["render", str(src), "--var", "name=Bob"])
        pclc_result = runner.invoke(app, ["render", str(pclc), "--var", "name=Bob"])
        assert pcl_result.exit_code == 0
        assert pclc_result.exit_code == 0
        assert pcl_result.output == pclc_result.output
