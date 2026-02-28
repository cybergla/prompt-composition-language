"""CLI tests — written spec-first (TDD).

Uses typer.testing.CliRunner so no subprocess overhead.
"""

import pytest
from pathlib import Path
from typer.testing import CliRunner

from pcl.cli import app

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
