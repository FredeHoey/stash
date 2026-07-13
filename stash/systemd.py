from __future__ import annotations

from pathlib import Path
import subprocess
import sys


SERVICE_NAME = "stash.service"


class SystemdInstallError(RuntimeError):
    pass


def _quote_argument(value: str | Path) -> str:
    escaped = str(value).replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render_user_service(
    config_path: Path,
    dotfiles: Path,
    python_executable: Path | None = None,
) -> str:
    executable = python_executable or Path(sys.executable)
    command = " ".join(
        _quote_argument(argument)
        for argument in (
            executable,
            "-m",
            "stash.main",
            "--config",
            config_path.resolve(),
            "--dotfiles",
            dotfiles.resolve(),
            "daemon",
        )
    )
    return f"""[Unit]
Description=Live stash configuration

[Service]
Type=simple
ExecStart={command}
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
"""


def install_user_service(
    config_path: Path,
    dotfiles: Path,
    unit_path: Path | None = None,
    python_executable: Path | None = None,
) -> Path:
    destination = unit_path or Path.home() / ".config/systemd/user" / SERVICE_NAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    service = render_user_service(config_path, dotfiles, python_executable)
    temporary_path = destination.with_name(f".{destination.name}.tmp")
    temporary_path.write_text(service)
    temporary_path.replace(destination)

    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", SERVICE_NAME], check=True)
        subprocess.run(["systemctl", "--user", "restart", SERVICE_NAME], check=True)
    except FileNotFoundError as exc:
        raise SystemdInstallError("systemctl is not installed") from exc
    except subprocess.CalledProcessError as exc:
        raise SystemdInstallError(
            f"systemctl command failed with exit code {exc.returncode}"
        ) from exc

    return destination
