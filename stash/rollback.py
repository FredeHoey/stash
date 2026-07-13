from __future__ import annotations

from pathlib import Path
from typing import Iterable
from uuid import UUID

from stash.deployment import atomic_symlink
from stash.repositories import DotfileModuleRepository


class RollbackError(RuntimeError):
    pass


def rollback_to_generation(
    generation_id: UUID,
    module_repo: DotfileModuleRepository,
    modules: Iterable[str] | None = None,
) -> dict[str, Path]:
    module_records = module_repo.get_by_generation(generation_id)
    if not module_records:
        raise RollbackError(f"No modules found for generation {generation_id}")

    module_lookup = {record.module_name: record for record in module_records}
    if modules is None:
        selected = list(module_lookup.values())
    else:
        missing = [name for name in modules if name not in module_lookup]
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise RollbackError(
                f"Missing modules for generation {generation_id}: {missing_list}"
            )
        selected = [module_lookup[name] for name in modules]

    updated: dict[str, Path] = {}
    for record in selected:
        target_path = Path(record.target_path).expanduser()
        rendered_path = Path(record.output_path)
        if not rendered_path.exists():
            raise RollbackError(
                f"Rendered path missing for {record.module_name}: {rendered_path}"
            )
        atomic_symlink(target_path, rendered_path)
        updated[record.module_name] = rendered_path

    return updated
