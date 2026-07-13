from pathlib import Path
import subprocess

from stash.systemd import install_user_service, render_user_service


def test_render_user_service_quotes_paths(tmp_path: Path):
    service = render_user_service(
        tmp_path / "dot files" / "config%name.yaml",
        tmp_path / "dot files",
        tmp_path / "virtual env" / "python",
    )

    assert '"-m" "stash.main"' in service
    assert '"--config"' in service
    assert "config%%name.yaml" in service
    assert '"--dotfiles"' in service
    assert '"daemon"' in service
    assert "Type=dbus" in service
    assert "BusName=org.dotstash.Stash" in service


def test_install_user_service_reloads_enables_and_restarts(tmp_path: Path, monkeypatch):
    commands: list[list[str]] = []

    def run(command: list[str], check: bool):
        assert check is True
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("stash.systemd.subprocess.run", run)
    unit_path = tmp_path / "systemd" / "stash.service"

    installed_path = install_user_service(
        tmp_path / "config.yaml",
        tmp_path / "dotfiles",
        unit_path=unit_path,
        python_executable=Path("/venv/bin/python"),
    )

    assert installed_path == unit_path
    assert unit_path.read_text().startswith("[Unit]\n")
    assert commands == [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "stash.service"],
        ["systemctl", "--user", "restart", "stash.service"],
    ]
