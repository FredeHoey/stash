from pathlib import Path

from stash.cleanup import clean_orphan_generations
from stash.db import get_session, init_db
from stash.repositories import DotfileModuleRepository, GenerationRepository


def test_clean_orphan_generations(tmp_path: Path):
    db_path = tmp_path / "stash.sqlite"
    render_root = tmp_path / "rendered"
    init_db(db_path)

    with get_session(db_path) as session:
        generation_repo = GenerationRepository(session)
        module_repo = DotfileModuleRepository(session)
        orphan = generation_repo.create(description="orphan")
        retained = generation_repo.create(description="retained")
        module_repo.create(
            generation_id=retained.id,
            module_name="alpha",
            output_path=render_root / "alpha" / str(retained.id),
            target_path=tmp_path / "target" / "alpha",
        )

    orphan_dir = render_root / "alpha" / str(orphan.id)
    orphan_dir.mkdir(parents=True)
    (orphan_dir / "file.txt").write_text("data")

    with get_session(db_path) as session:
        generation_repo = GenerationRepository(session)
        module_repo = DotfileModuleRepository(session)
        deleted = clean_orphan_generations(generation_repo, module_repo, render_root)

    assert deleted == [orphan.id]
    assert not orphan_dir.exists()

    with get_session(db_path) as session:
        generation_repo = GenerationRepository(session)
        module_repo = DotfileModuleRepository(session)
        remaining = generation_repo.get(retained.id)
        assert remaining is not None
        assert module_repo.get_by_generation(retained.id)


def test_clean_removes_stale_modules(tmp_path: Path):
    db_path = tmp_path / "stash.sqlite"
    render_root = tmp_path / "rendered"
    init_db(db_path)

    with get_session(db_path) as session:
        generation_repo = GenerationRepository(session)
        module_repo = DotfileModuleRepository(session)
        older = generation_repo.create(description="older")
        newer = generation_repo.create(description="newer")
        module_repo.create(
            generation_id=older.id,
            module_name="alpha",
            output_path=render_root / "alpha" / str(older.id),
            target_path=tmp_path / "target" / "alpha",
        )
        module_repo.create(
            generation_id=newer.id,
            module_name="alpha",
            output_path=render_root / "alpha" / str(newer.id),
            target_path=tmp_path / "target" / "alpha",
        )

    with get_session(db_path) as session:
        generation_repo = GenerationRepository(session)
        module_repo = DotfileModuleRepository(session)
        deleted = clean_orphan_generations(generation_repo, module_repo, render_root)

    assert deleted == [older.id]

    with get_session(db_path) as session:
        module_repo = DotfileModuleRepository(session)
        remaining = module_repo.get_by_generation(newer.id)
        assert len(remaining) == 1
        assert remaining[0].module_name == "alpha"
