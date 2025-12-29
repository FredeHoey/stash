from pathlib import Path
from sqlalchemy.types import TypeDecorator, String


class PathType(TypeDecorator):
    """SQLAlchemy type for storing pathlib.Path as strings using forward slashes."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Convert Path to string (posix-style with forward slashes)."""
        if value is None:
            return None
        if isinstance(value, Path):
            return value.as_posix()
        return str(value)

    def process_result_value(self, value, dialect):
        """Convert string back to Path."""
        if value is None:
            return None
        return Path(value)
