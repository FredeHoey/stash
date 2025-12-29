from pathlib import Path
from uuid import UUID

from stash.models import DotfileModule, RenderedFile


def test_dotfile_module_validation():
    module = DotfileModule(
        id=1,
        generation_id=UUID("b7f1d5f8-87f7-4c49-8f45-2c4aa7b5f4b7"),
        module_name=" test ",
        output_path=Path("~/rendered/test"),
        target_path=Path("~/target"),
    )

    assert module.module_name == "test"
    assert module.normalized_output_path().is_absolute()


def test_rendered_file_validation():
    rendered = RenderedFile(
        id=1,
        module_id=1,
        file_path=Path("~/rendered/test/file"),
        template_path=Path("~/templates/file"),
        content_hash="abc",
    )

    assert rendered.file_path.is_absolute()
    assert rendered.template_path.is_absolute()
