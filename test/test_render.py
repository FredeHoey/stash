from pathlib import Path

from stash.db import get_session, init_db
from stash.render import render_dotfiles
from stash.repositories import (
    DotfileModuleRepository,
    GenerationRepository,
    RenderedFileRepository,
)


def test_render(tmp_path: Path):
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

        updated = render_dotfiles(
            Path(__file__).parent / "assets/dotfiles/test_config",
            "test",
            target,
            variables,
            render_root,
            generation.id,
            module_repo=module_repo,
            rendered_file_repo=rendered_file_repo,
        )

        assert updated is True

    rendered_module_dir = render_root / "test" / str(generation.id)
    assert (rendered_module_dir / "test_file.ini").exists()
    assert (rendered_module_dir / "test_file.json").exists()
    assert (target / "test_file.ini").is_symlink()
    assert (target / "test_file.json").is_symlink()
    assert (target / "test_file.ini").resolve() == (
        rendered_module_dir / "test_file.ini"
    )
    assert (target / "test_file.json").resolve() == (
        rendered_module_dir / "test_file.json"
    )
