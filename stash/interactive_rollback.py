from __future__ import annotations

import questionary

from stash.models import DotfileModule, Generation
from stash.repositories import DotfileModuleRepository, GenerationRepository
from stash.rollback import RollbackError, rollback_to_generation


def interactive_rollback(
    generation_repo: GenerationRepository, module_repo: DotfileModuleRepository
) -> dict[str, str] | None:
    generation_models = list(generation_repo.get_all())
    if not generation_models:
        return None

    generation_choices = [
        questionary.Choice(
            title=f"{generation.id} ({generation.created_at:%Y-%m-%d %H:%M})",
            value=generation,
        )
        for generation in generation_models
    ]

    selected_generation = questionary.select(
        "Select generation to rollback:", choices=generation_choices
    ).ask()
    if selected_generation is None:
        return None

    module_models = list(module_repo.get_by_generation(selected_generation.id))
    if not module_models:
        return None

    scope = questionary.select(
        "Rollback scope:", choices=["all modules", "select modules"]
    ).ask()
    if scope is None:
        return None

    selected_modules: list[str] | None
    if scope == "select modules":
        selected_modules = questionary.checkbox(
            "Select modules:",
            choices=[module.module_name for module in module_models],
            validate=lambda selected: len(selected) > 0 or "Select at least one module",
        ).ask()
        if not selected_modules:
            return None
    else:
        selected_modules = None

    if not questionary.confirm("Proceed with rollback?", default=False).ask():
        return None

    try:
        updated = rollback_to_generation(
            selected_generation.id, module_repo, modules=selected_modules
        )
    except RollbackError:
        raise

    return {name: path.as_posix() for name, path in updated.items()}
