from __future__ import annotations

from pathlib import Path
from uuid import UUID

from stash.repositories import DotfileModuleRepository, GenerationRepository


class CleanupError(RuntimeError):
    pass


def _remove_generation_dir(render_root: Path, generation_id: UUID) -> None:
    if not render_root.exists():
        return
    for module_dir in render_root.iterdir():
        generation_dir = module_dir / str(generation_id)
        if generation_dir.exists():
            for path in generation_dir.rglob("*"):
                if path.is_file() or path.is_symlink():
                    path.unlink()
            for path in sorted(generation_dir.rglob("*"), reverse=True):
                if path.is_dir():
                    path.rmdir()
            if generation_dir.exists():
                generation_dir.rmdir()


def cleanup_generations(
    keep: int,
    generation_repo: GenerationRepository,
    render_root: Path,
) -> list[UUID]:
    if keep < 1:
        raise CleanupError("keep must be at least 1")

    generations = generation_repo.get_all()
    to_delete = generations[keep:]
    deleted: list[UUID] = []

    for generation in to_delete:
        generation_id = generation.id
        generation_repo.delete(generation)
        deleted.append(generation_id)
        _remove_generation_dir(render_root, generation_id)

    return deleted


def clean_orphan_generations(
    generation_repo: GenerationRepository,
    module_repo: DotfileModuleRepository,
    render_root: Path,
) -> list[UUID]:
    module_repo.delete_stale_modules()
    orphaned = generation_repo.get_without_modules(module_repo)
    deleted: list[UUID] = []

    for generation in orphaned:
        generation_id = generation.id
        generation_repo.delete(generation)
        deleted.append(generation_id)
        _remove_generation_dir(render_root, generation_id)

    return deleted
