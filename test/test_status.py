from pathlib import Path

from stash.db import get_session, init_db
from stash.render import render_dotfiles
from stash.repositories import (
    DotfileModuleRepository,
    GenerationRepository,
    RenderedFileRepository,
)
from stash.status import collect_status


def test_status_detects_dirty_file(tmp_path: Path):
    render_root = tmp_path / "rendered"
    target = tmp_path / "deployed"
    module_dir = tmp_path / "module"
    module_dir.mkdir()

    (module_dir / "dot_config").write_text("value={{ value }}")

    db_path = tmp_path / "stash.sqlite"
    init_db(db_path)

    with get_session(db_path) as session:
        generation_repo = GenerationRepository(session)
        module_repo = DotfileModuleRepository(session)
        rendered_file_repo = RenderedFileRepository(session)

        generation = generation_repo.create()
        render_dotfiles(
            module_dir,
            "test",
            target,
            {"value": 1},
            render_root,
            generation.id,
            module_repo=module_repo,
            rendered_file_repo=rendered_file_repo,
        )

        statuses = collect_status(module_repo, rendered_file_repo)
        assert statuses
        assert statuses[0].dirty is False

        target_path = statuses[0].file_path
        target_path.write_text("changed")

        statuses = collect_status(module_repo, rendered_file_repo)
        assert statuses[0].dirty is True
        assert statuses[0].file_path == target / ".config"


def test_status_skips_stale_modules(tmp_path: Path):
    render_root = tmp_path / "rendered"
    target = tmp_path / "deployed"
    module_dir = tmp_path / "module"
    module_dir.mkdir()

    (module_dir / "dot_config").write_text("value={{ value }}")

    db_path = tmp_path / "stash.sqlite"
    init_db(db_path)

    with get_session(db_path) as session:
        generation_repo = GenerationRepository(session)
        module_repo = DotfileModuleRepository(session)
        rendered_file_repo = RenderedFileRepository(session)

        generation_old = generation_repo.create()
        render_dotfiles(
            module_dir,
            "test",
            target,
            {"value": 1},
            render_root,
            generation_old.id,
            module_repo=module_repo,
            rendered_file_repo=rendered_file_repo,
        )

        generation_new = generation_repo.create()
        render_dotfiles(
            module_dir,
            "test",
            target,
            {"value": 2},
            render_root,
            generation_new.id,
            module_repo=module_repo,
            rendered_file_repo=rendered_file_repo,
        )

        statuses = collect_status(module_repo, rendered_file_repo)
        assert len(statuses) == 1
        assert statuses[0].generation_id == generation_new.id
