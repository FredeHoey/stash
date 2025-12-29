from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Iterable
from uuid import UUID

from rich.console import Console
from rich.table import Table

from stash.models import DotfileModule, RenderedFile
from stash.repositories import DotfileModuleRepository, RenderedFileRepository


@dataclass(frozen=True)
class RenderStatus:
    module_name: str
    generation_id: UUID
    file_path: Path
    rendered_path: Path
    content_hash: str
    dirty: bool


def _hash_file(path: Path) -> str | None:
    if not path.exists():
        return None
    if path.is_symlink():
        path = path.resolve()
    if not path.exists() or not path.is_file():
        return None
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_status(
    module_repo: DotfileModuleRepository,
    rendered_file_repo: RenderedFileRepository,
) -> list[RenderStatus]:
    statuses: list[RenderStatus] = []
    seen_modules: set[str] = set()
    for module in module_repo.get_all():
        if module.module_name in seen_modules:
            continue
        seen_modules.add(module.module_name)
        statuses.extend(_collect_module_status(module, rendered_file_repo))
    return statuses


def _collect_module_status(
    module: DotfileModule,
    rendered_file_repo: RenderedFileRepository,
) -> list[RenderStatus]:
    rendered_files = rendered_file_repo.get_by_module(module.id)
    statuses: list[RenderStatus] = []

    for rendered in rendered_files:
        relative = rendered.file_path.relative_to(module.output_path)
        file_path = module.target_path / relative
        current_hash = _hash_file(file_path)
        dirty = current_hash is None or current_hash != rendered.content_hash
        statuses.append(
            RenderStatus(
                module_name=module.module_name,
                generation_id=module.generation_id,
                file_path=file_path,
                rendered_path=rendered.file_path,
                content_hash=rendered.content_hash,
                dirty=dirty,
            )
        )

    return statuses


def render_status(statuses: Iterable[RenderStatus]) -> None:
    table = Table(title="Stash Status", show_lines=False)
    table.add_column("Module", style="cyan")
    table.add_column("Generation", style="green", width=36)
    table.add_column("Target", style="white")
    table.add_column("Dirty", style="magenta", width=5)

    for status in statuses:
        table.add_row(
            status.module_name,
            str(status.generation_id),
            status.file_path.as_posix(),
            "yes" if status.dirty else "no",
        )

    console = Console()
    console.print(table)


def render_status_json(statuses: Iterable[RenderStatus]) -> None:
    payload = [
        {
            "module": status.module_name,
            "generation_id": str(status.generation_id),
            "target_path": status.file_path.as_posix(),
            "rendered_path": status.rendered_path.as_posix(),
            "content_hash": status.content_hash,
            "dirty": status.dirty,
        }
        for status in statuses
    ]
    console = Console()
    console.print_json(data=payload)
