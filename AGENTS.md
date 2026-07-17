# Repository Guidelines (stash)

## Purpose
- This file guides coding agents working in this repository.
- Prefer small, targeted changes that preserve the current architecture.
- Optimize for simplicity, readability, explicit errors, reasonable performance, and CLI usability.

## Project Structure
- `stash/main.py`: CLI entrypoint and command dispatch.
- `stash/daemon.py`: long-running daemon loop, file watching, D-Bus startup, theme state, reload flow.
- `stash/live.py`: live render reconciliation, incremental template invalidation, symlink deployment, and cleanup of stale outputs.
- `stash/dbus_service.py`: D-Bus interface definition and dynamic CLI command metadata.
- `stash/dbus_client.py`: client-side D-Bus calls used by top-level CLI commands such as `ping`, `reload`, `get-theme`, `set-theme`, `list-themes`, and `stop`.
- `stash/hooks.py`: hook discovery, hook templating, process execution, and hook error handling.
- `stash/config.py`: config loading, config writing, theme resolution, and template variable preparation.
- `stash/templates.py`: Jinja environment and template rendering helpers.
- `stash/deployment.py`: filesystem deployment helpers such as atomic symlink replacement.
- `stash/systemd.py`: rendered user service installation and `systemctl` orchestration.
- `stash/adopt.py`: adopt command helpers for copying existing files into managed modules.
- `stash/formats.py`: format validation helpers.
- `test/`: pytest suite.
- `test/assets/`: fixture inputs for templates and format validation.
- `config.yaml`: default config file name, typically resolved relative to the chosen dotfiles root unless `--config` is provided.

## Daemon Architecture
- `stash daemon` is the center of the application.
- The daemon acquires a lock under the live render root so only one daemon instance is active.
- It loads `config.yaml`, resolves the initial theme, renders all configured modules into the live tree, and atomically points target symlinks at those rendered files.
- It watches the dotfiles tree and, when needed, the config parent directory with `inotify`.
- Relevant changes are reconciled incrementally when possible. Template file changes, template dependency changes, and changed template variables from config updates should rerender only the affected outputs and their dependency fallout.
- Initial config or render failures abort daemon startup.
- Reload-time config, render, and YAML failures are reported, and the previously deployed live state remains active.
- The daemon owns `org.dotstash.Stash` on the user session bus and exposes methods through `stash/dbus_service.py`.
- Top-level CLI commands such as `stash reload` and `stash set-theme dark` are D-Bus clients generated from the decorated service methods. Keep service and CLI behavior aligned.
- Hook execution is attached to D-Bus method calls. Pre-hooks can block an action.
- Post-hooks run after the underlying action succeeds, but a post-hook failure is still returned to the caller as an error even though the action already happened.

## Design Priorities

### Simplicity
- Prefer straightforward control flow over abstraction-heavy designs.
- Keep data flow easy to trace between CLI, daemon, render, D-Bus, and hook layers.
- Do not introduce new framework-style layers for small features.

### Readability
- Write code that can be understood quickly from the file where it lives.
- Use descriptive names for state and filesystem paths.
- Prefer small helper functions when they reduce cognitive load, not just line count.
- Keep module boundaries clear: config logic in `config.py`, render logic in `live.py` and `templates.py`, D-Bus concerns in `dbus_service.py` and `dbus_client.py`.

### Error Handling
- Raise explicit `ValueError`, `RuntimeError`, or repo-specific error types with direct messages.
- Do not silently swallow exceptions.
- Preserve the current pattern of wrapping lower-level failures with user-facing context.
- For CLI-visible failures, prefer messages that tell the user what failed, not just the exception class.
- Fail safely around filesystem operations. Avoid partial destructive updates when a render or deployment step fails.

### Performance
- Keep the steady-state daemon path cheap.
- Avoid unnecessary filesystem scans, repeated config parsing inside tight loops, or invalidation that rerenders more templates than required.
- Preserve atomic replacement patterns for deployed symlinks and rendered directories.
- Use `pathlib.Path` and direct filesystem operations instead of shelling out when Python can do the job clearly.

### Usability
- CLI output should stay concise and actionable.
- Follow existing `print()`-based user messaging unless there is a strong reason to change it.
- New commands should fit the existing CLI and D-Bus command model rather than adding inconsistent entrypoints.
- Validation errors should be understandable to someone editing `config.yaml` by hand.

## Environment & Dependencies
- Python version: `>=3.14` (see `.python-version` and `pyproject.toml`).
- Primary runtime dependencies include `dbus-fast`, `inotify`, `jinja2`, `pyyaml`, and `questionary`.
- Install development dependencies with one of:
  - `pip install -e .[dev]`
  - `uv sync`
- CLI entrypoint: `stash` → `stash.main:main`.

## Build, Lint, Type Check, Test

### Build
- `python -m build`

### Lint + Format
- `ruff check .`
- `ruff check --fix .`
- `ruff format .`
- `ruff format --check .`

### Type Check
- `pyright`

### Tests
- Full suite: `pytest`
- Single file examples:
  - `pytest test/test_daemon.py`
  - `pytest test/test_dbus_service.py`
  - `pytest test/test_hooks.py`
- Single test examples:
  - `pytest test/test_dbus_service.py::test_get_theme_returns_active_name`
  - `pytest test/test_daemon.py::test_render_live_updates_links_without_generations`
- Pattern runs:
  - `pytest -k "theme"`
  - `pytest -k "dbus"`

## Coding Conventions

### Imports
- Standard library first, third-party second, local imports last.
- Prefer explicit imports.

### Formatting
- 4-space indentation, no tabs.
- Let Ruff own formatting.
- Avoid trailing whitespace and avoid blank-line noise.

### Types
- Add type hints where they clarify inputs, outputs, or persistent state.
- Prefer concrete types such as `dict[str, Any]`, `list[Path]`, and `frozenset[Path]`.
- Avoid `# type: ignore` unless there is no practical alternative and the reason is documented.

### Naming
- Files, functions, and variables: snake_case.
- Classes: PascalCase.
- Avoid one-letter variables except in tiny local scopes.
- Keep method and handler names consistent across CLI and D-Bus when they represent the same action.

### Paths and Filesystem Work
- Prefer `pathlib.Path`.
- Use `Path.open()`, `Path.write_text()`, and `Path.resolve()` consistently.
- Be careful with symlinks, atomic replacements, and directory removal.
- Never clobber a real directory when the code expects to replace only a symlink or file.

## Templates, Themes, and Hooks
- Jinja rendering uses `StrictUndefined`. Missing template variables should fail loudly.
- Themes use Base16 names and are resolved through `stash.config.resolve_theme`.
- The active theme is daemon state. Changes through D-Bus affect the daemon lifetime, not the sample config file.
- Hook directories are resolved relative to the dotfiles repository and must stay within it.
- Hook files are rendered as templates before execution. Treat hook templating errors as first-class failures.
- Pre-hooks and post-hooks are part of observable behavior. Preserve their ordering and semantics.

## Tests & Fixtures
- Tests live in `test/` and are named `test_*.py`.
- Use `tmp_path` for filesystem tests.
- Do not write to real home directories in tests.
- Add or update tests when behavior changes, especially for:
  - D-Bus command registration
  - daemon reload and theme behavior
  - live render deployment and stale-link cleanup
  - hook lifecycle and failure reporting
  - config validation and theme validation

## Change Management
- Keep changes minimal and scoped to the request.
- Avoid refactors unless they materially improve clarity or are required for correctness.
- Preserve public behavior unless the user asked to change it.
- When changing architecture-sensitive code, prefer extending existing patterns over replacing them.

## Validation Checklist
- Run relevant pytest tests for touched modules.
- Run `ruff check .` and `ruff format --check .`.
- Run `pyright` for type-sensitive changes.
- If you touch daemon, D-Bus, hooks, or render behavior, verify both success paths and failure paths.
