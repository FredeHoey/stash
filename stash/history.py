from __future__ import annotations

from datetime import datetime
from typing import Iterable
from uuid import UUID

from rich.console import Console
from rich.table import Table

from stash.models import Generation
from stash.repositories import DotfileModuleRepository, GenerationRepository


def render_history_from_repo(
    generation_repo: GenerationRepository,
    module_repo: DotfileModuleRepository,
    as_json: bool = False,
    module: str | None = None,
) -> None:
    generations = generation_repo.get_all()
    render_history(generations, module_repo, as_json=as_json, module=module)


def render_history(
    generations: Iterable[Generation],
    module_repo: DotfileModuleRepository,
    as_json: bool = False,
    module: str | None = None,
) -> None:
    if as_json:
        console = Console()
        payload = []
        for generation in generations:
            module_names = _module_names(module_repo, generation.id, module)
            if module_names is None:
                continue
            payload.append(
                {
                    "id": str(generation.id),
                    "created_at": generation.created_at.isoformat(),
                    "description": generation.description,
                    "modules": module_names,
                }
            )
        console.print_json(data=payload)
        return

    table = Table(title="Generation History", show_lines=False)
    table.add_column("ID", style="cyan", width=36, no_wrap=True)
    table.add_column("Created", style="green", width=20)
    table.add_column("Description", style="white")
    table.add_column("Modules", style="magenta")

    for generation in generations:
        module_names = _module_names(module_repo, generation.id, module)
        if module_names is None:
            continue
        created = _format_timestamp(generation.created_at)
        modules_display = ", ".join(module_names)
        table.add_row(
            str(generation.id),
            created,
            generation.description or "",
            modules_display,
        )

    console = Console()
    console.print(table)


def _module_names(
    module_repo: DotfileModuleRepository,
    generation_id: UUID,
    module: str | None,
) -> list[str] | None:
    records = module_repo.get_by_generation(generation_id)
    names = [record.module_name for record in records]
    if module is None:
        return sorted(names)
    if module in names:
        return [module]
    return None


def _format_timestamp(value: datetime) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")
