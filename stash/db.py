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

@contextmanager
def get_session(db_path: Path | None = None) -> Generator[Session, None, None]:
    target_path = db_path or _DEFAULT_DB_PATH.expanduser()

    config = Config()

    migrations_root = importlib.resources.files("migrations")
    config.set_main_option("script_location", str(migrations_root))

    config.set_main_option("sqlalchemy.url", f"sqlite:///{target_path}")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{target_path}", future=True)
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
