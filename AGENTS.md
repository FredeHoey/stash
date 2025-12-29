# Repository Guidelines (stash)

## Purpose
- This file guides agentic coding assistants working in this repo.
- Follow local patterns, keep changes minimal, and prefer explicit errors.

## Project Structure & Module Organization
- `stash/` holds application logic.
  - `stash/main.py`: CLI entry, config loading, orchestration.
  - `stash/render.py`: Jinja rendering + symlink wiring.
  - `stash/formats.py`: format validation helpers.
  - `stash/database.py`: Pydantic model stubs.
- `test/` contains pytest suites.
  - `test/assets/` holds fixture templates and config inputs.
- `config.yaml` in repo root is sample config, not production.

## Environment & Dependencies
- Python version: `>=3.14` (see `.python-version`).
- Install dev deps (choose one):
  - `pip install -e .[dev]`
  - `uv sync`
- Script entrypoint: `stash` → `stash.main:main` (see `pyproject.toml`).

## Build, Lint, Type Check, Test
### Build
- Build distributions:
  - `python -m build`

### Lint + Format (Ruff)
- Lint:
  - `ruff check .`
  - `ruff check --fix .` (apply auto-fixes)
- Format:
  - `ruff format .`
  - `ruff format --check .`
  - `ruff format --diff .`

### Type Checking
- `pyright`

### Tests (Pytest)
- Run all tests:
  - `pytest`
- Run a single file:
  - `pytest test/test_render.py`
  - `pytest test/test_formats.py`
- Run a single test:
  - `pytest test/test_render.py::test_render`
  - `pytest test/test_formats.py::test_json_validator`
- Run by name pattern:
  - `pytest -k "render"`
  - `pytest -k "json"`
- Re-run failed tests:
  - `pytest --lf`
  - `pytest --ff`
- Stop on first failure:
  - `pytest -x`
- Verbose output:
  - `pytest -v`
  - `pytest -vv`

## Coding Style & Conventions
### Imports
- Standard library first, third-party second, local imports last.
- Prefer explicit imports over `import *`.

### Formatting
- 4-space indentation, no tabs.
- Keep lines readable; let `ruff format` enforce formatting.
- Avoid trailing whitespace and extra blank lines.

### Types
- Use type hints where practical (see `render.py`).
- Prefer concrete types (`dict[str, Any]`) over `dict`.
- Avoid type suppression (`as any`, `# type: ignore`).

### Naming
- Files: snake_case.
- Functions and variables: snake_case.
- Classes: PascalCase.
- Avoid one-letter variables unless in tiny local scopes.

### Path Handling
- Prefer `pathlib.Path` for filesystem operations.
- Use `Path.open()` and `Path.write_text()`.

### Error Handling
- Raise explicit errors for invalid config or invalid states.
- Do not swallow exceptions silently.
- Prefer explicit messaging for user-facing CLI errors.

### Logging/Output
- Current code uses `print()` for CLI output. Follow that pattern.
- If adding logging, keep it minimal and consistent.

## Template & Rendering Behavior
- Jinja environment uses `StrictUndefined` to surface missing variables.
- Rendered templates are written under render root and symlinked to targets.
- Avoid clobbering real directories; raise if target is a directory.

## Tests & Fixtures
- Tests live in `test/` and are named `test_*.py`.
- Fixture assets live in `test/assets/`.
- For new template features:
  - Add sample templates under `test/assets/dotfiles/<module>/`.
  - Assert renders exist under render root.
  - Confirm targets are symlinks pointing to rendered files.

## Configuration & Safety
- Do not commit real secrets into fixtures or `config.yaml`.
- Avoid writing to real home directories in tests.
- Use `tmp_path` for filesystem fixtures in pytest.

## Repo-Specific Notes
- `pyproject.toml` is the single source of tool configuration.
- No `tox.ini`, `noxfile`, or `pytest.ini` present.
- No Cursor rules (`.cursor/rules/`, `.cursorrules`) found.
- No Copilot rules (`.github/copilot-instructions.md`) found.

## Change Management
- Keep changes minimal and scoped to the request.
- Avoid refactors when fixing a specific bug.
- Update tests when behavior changes.

## Validation Checklist
- Run relevant unit tests for touched modules.
- Run `ruff check .` and `ruff format .` after code changes.
- Run `pyright` if type-sensitive changes were made.
