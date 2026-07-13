from pathlib import Path


def atomic_symlink(link_path: Path, rendered_path: Path) -> None:
    if link_path.exists() or link_path.is_symlink():
        if link_path.is_dir() and not link_path.is_symlink():
            raise IsADirectoryError(
                f"Cannot replace directory at {link_path} with a symlink"
            )
        link_path.unlink()
    link_path.parent.mkdir(parents=True, exist_ok=True)
    temp_link = link_path.with_name(f"{link_path.name}.tmp")
    if temp_link.exists() or temp_link.is_symlink():
        temp_link.unlink()
    temp_link.symlink_to(rendered_path)
    temp_link.replace(link_path)
