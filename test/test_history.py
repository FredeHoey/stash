from datetime import datetime
from datetime import datetime
import json
from pathlib import Path

from stash.db import get_session, init_db
from stash.history import render_history
from stash.repositories import DotfileModuleRepository, GenerationRepository


def test_history_json_output(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.setenv("RICH_DISABLE", "1")
    db_path = tmp_path / "stash.sqlite"
    init_db(db_path)

    created_first = datetime(2024, 1, 1, 12, 0, 0)
    created_second = datetime(2024, 1, 2, 12, 0, 0)

    with get_session(db_path) as session:
        generation_repo = GenerationRepository(session)
        module_repo = DotfileModuleRepository(session)
        first = generation_repo.create(description="first")
        second = generation_repo.create(description="second")
        module_repo.create(
            generation_id=first.id,
            module_name="alpha",
            output_path=tmp_path / "rendered" / "first",
            target_path=tmp_path / "target" / "first",
        )
        module_repo.create(
            generation_id=second.id,
            module_name="beta",
            output_path=tmp_path / "rendered" / "second",
            target_path=tmp_path / "target" / "second",
        )
        module_repo.create(
            generation_id=second.id,
            module_name="gamma",
            output_path=tmp_path / "rendered" / "second",
            target_path=tmp_path / "target" / "second",
        )
        first.created_at = created_first
        second.created_at = created_second

    with get_session(db_path) as session:
        generation_repo = GenerationRepository(session)
        module_repo = DotfileModuleRepository(session)
        generations = generation_repo.get_all()
        render_history(generations, module_repo, as_json=True)

    output = capsys.readouterr().out.strip()
    payload = json.loads(output)

    assert payload == [
        {
            "id": str(second.id),
            "created_at": created_second.isoformat(),
            "description": "second",
            "modules": ["beta", "gamma"],
        },
        {
            "id": str(first.id),
            "created_at": created_first.isoformat(),
            "description": "first",
            "modules": ["alpha"],
        },
    ]

    with get_session(db_path) as session:
        generation_repo = GenerationRepository(session)
        module_repo = DotfileModuleRepository(session)
        generations = generation_repo.get_all()
        render_history(generations, module_repo, as_json=True, module="beta")

    output = capsys.readouterr().out.strip()
    payload = json.loads(output)

    assert payload == [
        {
            "id": str(second.id),
            "created_at": created_second.isoformat(),
            "description": "second",
            "modules": ["beta"],
        }
    ]
