from pathlib import Path
from uuid import UUID

import pytest

from stash.db import get_session, init_db
from stash.repositories import DotfileModuleRepository, GenerationRepository
from stash.rollback import RollbackError, rollback_to_generation


def test_rollback_missing_generation(tmp_path: Path):
    db_path = tmp_path / "stash.sqlite"
    init_db(db_path)

    with get_session(db_path) as session:
        module_repo = DotfileModuleRepository(session)
        with pytest.raises(RollbackError):
            rollback_to_generation(
                UUID("a5d5e2fa-3d23-48b7-aaf4-f7b8e3e9c8b2"),
                module_repo,
            )


def test_rollback_updates_symlink(tmp_path: Path):
    db_path = tmp_path / "stash.sqlite"
    init_db(db_path)

    render_root = tmp_path / "rendered"
    target_root = tmp_path / "target"

    with get_session(db_path) as session:
        generation_repo = GenerationRepository(session)
        module_repo = DotfileModuleRepository(session)
        generation = generation_repo.create()
        module = module_repo.create(
            generation_id=generation.id,
            module_name="test",
            output_path=str(render_root / "test" / str(generation.id)),
            target_path=str(target_root),
        )

    rendered_path = Path(module.output_path)
    rendered_path.mkdir(parents=True, exist_ok=True)
    rendered_file = rendered_path / "file.txt"
    rendered_file.write_text("data")

    with get_session(db_path) as session:
        module_repo = DotfileModuleRepository(session)
        updated = rollback_to_generation(generation.id, module_repo)

    assert updated["test"].resolve() == rendered_path.resolve()
    assert target_root.is_symlink()
    assert target_root.resolve() == rendered_path.resolve()
