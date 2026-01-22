from __future__ import annotations

from typing import Any, Iterable

from rich.console import Console
from rich.table import Table

from stash.models import Generation
from stash.repositories import DotfileModuleRepository, GenerationRepository


def render_history_from_repo(
    generation_repo: GenerationRepository,
    module_repo: DotfileModuleRepository,
    as_json: bool = False,
    modules: set[str] = set(),
) -> None:
    generations = generation_repo.get_all()
    history = render_history(generations, module_repo, as_json=as_json, modules=modules)

    console = Console()
    if as_json:
        console.print_json(data=history)
        return

    table = Table(title="Generation History", show_lines=False)
    table.add_column("ID", style="cyan", width=36, no_wrap=True)
    table.add_column("Created", style="green", width=20)
    table.add_column("Description", style="white")
    table.add_column("Modules", style="magenta")

    for row in history:
        table.add_row(
            str(row["id"]),
            row["created_at"],
            row["description"],
            ", ".join(row["modules"]),
        )

    console.print(table)


def render_history(
    generations: Iterable[Generation],
    module_repo: DotfileModuleRepository,
    as_json: bool = False,
    modules: set[str] = set(),
) -> list[Any]:
    rows: list[dict[str, Any]] = []
    for generation in generations:
        records = module_repo.get_by_generation(generation.id)
        names = {record.module_name for record in records}
        rows.append(
            {
                "id": str(generation.id),
                "created_at": generation.created_at.isoformat(),
                "description": generation.description,
                "modules": sorted(
                    list(modules.intersection(names) if len(modules) else names)
                ),
            }
        )

    return rows
