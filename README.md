# PCL — Prompt Composition Language

PCL is a small DSL for authoring, composing, and managing LLM prompts as modular, version-controlled artifacts. A `.pcl` file compiles to a plain text string ready to use as a system prompt with any LLM API.

---

## Features

- **Blocks** — define named fragments with `@block name:`, include them with `@include`
- **Imports** — split prompts across files, import with `@import ./file.pcl [as ns]`
- **Variables** — `${var}` resolved at render time; `${var | default}` for fallbacks
- **Conditionals** — `@if variable:` / `@if not variable:` for truthiness-based branching
- **Raw blocks** — `@raw` / `@end` passes content through unmodified (no interpolation)
- **Comments** — lines starting with `#` are stripped from output
- **Frontmatter** — optional YAML metadata (`version`, `description`, arbitrary keys)

---

## Installation

Requires Python 3.11+. Uses [uv](https://github.com/astral-sh/uv) for environment management.

```bash
git clone <repo>
cd pcl
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Verify:

```bash
pcl --help
```

---

## CLI

### `pcl compile`

Compile a `.pcl` file and print the output. Variables with defaults are resolved; undefined variables with no default cause an error.

```bash
pcl compile examples/agent.pcl
```

### `pcl render`

Render a `.pcl` file with explicit variable values.

```bash
pcl render examples/agent.pcl \
  --var date=2026-02-28 \
  --var query="What is alignment?" \
  --var premium=true
```

Variables are passed as `key=value`. `true` and `false` are coerced to booleans.

### `pcl check`

Validate a `.pcl` file without producing output. Exits `0` on success, `1` on error.

```bash
pcl check examples/agent.pcl
```

### `pcl watch`

Recompile a file automatically whenever it changes. Accepts the same `--var` flags as `render`.

```bash
pcl watch examples/agent.pcl --var date=2026-02-28 --var premium=false
```

---

## Python API

```python
from pcl import compile, render

# Compile — parse and resolve imports; variables remain unresolved
template = compile("examples/agent.pcl")
print(template.metadata)   # {"version": 1.0, "description": "..."}

# Render — fully resolved output string
prompt = render("examples/agent.pcl", variables={
    "date": "2026-02-28",
    "query": "What is alignment?",
    "premium": True,
})
print(prompt)
```

---

## Language Quick Reference

```pcl
---
version: 1.0
description: Optional YAML frontmatter (not in output)
---

@import ./other.pcl
@import ./lib.pcl as lib

# This is a comment — stripped from output

@block intro:
    This block is defined but not yet emitted.

@include intro          # emit a local block
@include lib.greet      # emit a block from an imported file
@include other          # emit the entire body of other.pcl

@if premium:
    Shown only when premium is truthy.

@if not premium:
    Shown only when premium is falsy or absent.

Hello ${name}!                  # required variable
Hello ${name | world}!          # variable with default

@raw
${not_interpolated}  @not_a_directive
@end

\@block  →  literal @block in output
\#       →  literal # in output
\${      →  literal ${ in output
```

---

## Examples

The `examples/` directory contains a multi-file prompt:

| File | Purpose |
|------|---------|
| `examples/agent.pcl` | Main agent prompt — imports persona and tools |
| `examples/persona.pcl` | Persona blocks (`researcher`, `brief`) |
| `examples/tools.pcl` | Tool description blocks (`search`, `browse`, `premium_index`) |

Try it:

```bash
pcl render examples/agent.pcl \
  --var date=2026-02-28 \
  --var query="Explain quantum entanglement" \
  --var premium=false
```

---

## Running Tests

```bash
uv run pytest tests/ -v
```

With coverage:

```bash
uv run pytest tests/ --cov=pcl --cov-report=term-missing
```

---

## VS Code Extension

Syntax highlighting for `.pcl` files is in `vscode-extension/`. To install locally:

```bash
cp -r vscode-extension ~/.vscode/extensions/pcl-language-0.1.0
```

Then reload VS Code (`Cmd+Shift+P` → **Developer: Reload Window**).

---

## Project Structure

```
src/pcl/               ← Python package
  __init__.py          # compile, render exports
  parser.py            # line-by-line parser → AST
  compiler.py          # AST walker → string + metadata
  cli.py               # Typer app
  errors.py            # PCLError with line numbers
tests/
  test_parser.py
  test_compiler.py
  test_cli.py
examples/
  agent.pcl
  persona.pcl
  tools.pcl
vscode-extension/
  syntaxes/pcl.tmLanguage.json
  package.json
pyproject.toml
```
