from pathlib import Path

import pytest

from stash.adopt import adopt_files
from stash.config import ensure_dotfiles_module, load_config, write_config
from stash.db import get_session, init_db
from stash.repositories import (
    DotfileModuleRepository,
    GenerationRepository,
    RenderedFileRepository,
)


def test_adopt_files_renames_dotfiles(tmp_path: Path):
    dotfiles_root = tmp_path / "dotfiles"
    render_root = tmp_path / "rendered"
    dotfiles_root.mkdir()

    original = tmp_path / ".vimrc"
    original.write_text("set number")

    db_path = tmp_path / "stash.sqlite"
    init_db(db_path)

    with get_session(db_path) as session:
        generation_repo = GenerationRepository(session)
        module_repo = DotfileModuleRepository(session)
        rendered_file_repo = RenderedFileRepository(session)
        generation_id, module_dir = adopt_files(
            [original],
            "vim",
            dotfiles_root,
            render_root,
            generation_repo,
            module_repo,
            rendered_file_repo,
        )

    assert (module_dir / "dot_vimrc").exists()

    render_path = render_root / "vim" / str(generation_id)
    assert (render_path / ".vimrc").exists()

    assert original.is_symlink()
    assert original.resolve() == (render_path / ".vimrc").resolve()


def test_adopt_files_no_deploy(tmp_path: Path):
    dotfiles_root = tmp_path / "dotfiles"
    render_root = tmp_path / "rendered"
    dotfiles_root.mkdir()

    original = tmp_path / ".bashrc"
    original.write_text("export PATH=$PATH")

    db_path = tmp_path / "stash.sqlite"
    init_db(db_path)

    with get_session(db_path) as session:
        generation_repo = GenerationRepository(session)
        module_repo = DotfileModuleRepository(session)
        rendered_file_repo = RenderedFileRepository(session)
        generation_id, module_dir = adopt_files(
            [original],
            "shell",
            dotfiles_root,
            render_root,
            generation_repo,
            module_repo,
            rendered_file_repo,
            deploy=False,
        )

    assert generation_id is None
    assert (module_dir / "dot_bashrc").exists()
    assert not (render_root / "shell").exists()
    assert original.exists()
    assert not original.is_symlink()


def test_adopt_updates_config(tmp_path: Path):
    dotfiles_root = tmp_path / "dotfiles"
    dotfiles_root.mkdir()
    config_path = dotfiles_root / "config.yaml"
    config_path.write_text("dotfiles: {}\n")

    original = tmp_path / ".zshrc"
    original.write_text("export ZDOTDIR=$HOME")

    db_path = tmp_path / "stash.sqlite"
    init_db(db_path)

    with get_session(db_path) as session:
        generation_repo = GenerationRepository(session)
        module_repo = DotfileModuleRepository(session)
        rendered_file_repo = RenderedFileRepository(session)
        adopt_files(
            [original],
            "shell",
            dotfiles_root,
            tmp_path / "rendered",
            generation_repo,
            module_repo,
            rendered_file_repo,
        )

    config = load_config(config_path)
    config = ensure_dotfiles_module(config, "shell")
    write_config(config_path, config)

    updated = config_path.read_text()
    assert "shell" in updated


def test_adopt_files_directory(tmp_path: Path):
    dotfiles_root = tmp_path / "dotfiles"
    render_root = tmp_path / "rendered"
    dotfiles_root.mkdir()

    config_dir = tmp_path / ".config" / "tool"
    config_dir.mkdir(parents=True)
    (config_dir / ".settings.json").write_text("{}")
    (config_dir / ".env").write_text("KEY=VALUE")

    db_path = tmp_path / "stash.sqlite"
    init_db(db_path)

    with get_session(db_path) as session:
        generation_repo = GenerationRepository(session)
        module_repo = DotfileModuleRepository(session)
        rendered_file_repo = RenderedFileRepository(session)
        generation_id, module_dir = adopt_files(
            [config_dir],
            "tool",
            dotfiles_root,
            render_root,
            generation_repo,
            module_repo,
            rendered_file_repo,
        )

    assert (module_dir / "dot_settings.json").exists()
    assert (module_dir / "dot_env").exists()

    render_path = render_root / "tool" / str(generation_id)
    assert not (render_path / "dot_settings.json").exists()
    assert (render_path / ".settings.json").exists()
    assert (render_path / ".env").exists()

    assert (config_dir / ".settings.json").is_symlink()
    assert (config_dir / ".env").is_symlink()
