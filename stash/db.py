from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
import importlib.resources

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_DEFAULT_DB_PATH = Path("~/.local/state/stash/stash.sqlite")


def get_db_path() -> Path:
    return _DEFAULT_DB_PATH.expanduser()


def _ensure_db_dir(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)


def create_engine_for_path(db_path: Path):
    _ensure_db_dir(db_path)
    return create_engine(f"sqlite:///{db_path}", future=True)


def _alembic_config() -> Config:
    config = Config()
    migrations_root = importlib.resources.files("migrations")
    config.set_main_option("script_location", str(migrations_root))
    return config


def _stamp_if_needed(config: Config, db_path: Path) -> None:
    engine = create_engine_for_path(db_path)
    with engine.connect() as connection:
        result = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        )
        has_version_table = result.first() is not None
        if has_version_table:
            return

        result = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='generations'"
        )
        has_generations = result.first() is not None
        if not has_generations:
            return

    command.stamp(config, "head")


def init_db(db_path: Path | None = None) -> None:
    target_path = db_path or get_db_path()
    _ensure_db_dir(target_path)
    config = _alembic_config()
    config.set_main_option("sqlalchemy.url", f"sqlite:///{target_path}")
    _stamp_if_needed(config, target_path)
    command.upgrade(config, "head")


@contextmanager
def get_session(db_path: Path | None = None) -> Generator[Session, None, None]:
    target_path = db_path or get_db_path()
    engine = create_engine_for_path(target_path)
    session_factory = sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
