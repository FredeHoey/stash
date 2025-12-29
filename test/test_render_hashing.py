from pathlib import Path

from stash.db import get_session, init_db
from stash.render import render_dotfiles
from stash.repositories import (
    DotfileModuleRepository,
    GenerationRepository,
    RenderedFileRepository,
)


def test_render_skips_unchanged_module(tmp_path: Path):
    render_root = tmp_path / "rendered"
    target = tmp_path / "deployed"
    db_path = tmp_path / "stash.sqlite"
    variables = {"my_value": 42}

    init_db(db_path)

    with get_session(db_path) as session:
        generation_repo = GenerationRepository(session)
        module_repo = DotfileModuleRepository(session)
        rendered_file_repo = RenderedFileRepository(session)

        generation = generation_repo.create()
        updated_first = render_dotfiles(
            Path(__file__).parent / "assets/dotfiles/test_config",
            "test",
            target,
            variables,
            render_root,
            generation.id,
            module_repo=module_repo,
            rendered_file_repo=rendered_file_repo,
        )

        generation_next = generation_repo.create()
        updated_second = render_dotfiles(
            Path(__file__).parent / "assets/dotfiles/test_config",
            "test",
            target,
            variables,
            render_root,
            generation_next.id,
            module_repo=module_repo,
            rendered_file_repo=rendered_file_repo,
        )

        assert updated_first is True
        assert updated_second is False
