from pathlib import Path

from stash.adopt import adopt_files
from stash.config import add_dotfiles_module, load_config, write_config


def test_adopt_files_copies_dotfile_without_deploying(tmp_path: Path):
    dotfiles_root = tmp_path / "dotfiles"
    dotfiles_root.mkdir()
    original = tmp_path / ".vimrc"
    original.write_text("set number")

    module_dir, target_path = adopt_files([original], "vim", dotfiles_root)

    assert (module_dir / "dot_vimrc").read_text() == "set number"
    assert target_path == tmp_path
    assert original.exists()
    assert not original.is_symlink()


def test_adopt_files_preserves_directory_layout(tmp_path: Path):
    dotfiles_root = tmp_path / "dotfiles"
    dotfiles_root.mkdir()
    config_dir = tmp_path / ".config" / "tool"
    nested_dir = config_dir / "nested"
    nested_dir.mkdir(parents=True)
    (config_dir / ".settings.json").write_text("{}")
    (nested_dir / ".env").write_text("KEY=VALUE")

    module_dir, target_path = adopt_files([config_dir], "tool", dotfiles_root)

    assert target_path == config_dir
    assert (module_dir / "dot_settings.json").exists()
    assert (module_dir / "nested" / "dot_env").exists()


def test_add_dotfiles_module_records_adopt_target(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("dotfiles: {}\n")

    config = add_dotfiles_module(load_config(config_path), "shell", tmp_path)
    write_config(config_path, config)

    assert load_config(config_path)["dotfiles"]["shell"] == {
        "target": tmp_path.as_posix()
    }
