from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    validates,
)
from sqlalchemy.types import TypeDecorator


def _normalize_path(value: Path | str | None) -> Path | None:
    if value is None:
        return None
    path = value if isinstance(value, Path) else Path(value)
    path = path.expanduser()
    if not path.is_absolute():
        path = path.resolve()
    return path


class PathType(TypeDecorator):
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, Path):
            return value.as_posix()
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return Path(value)


class Base(DeclarativeBase):
    pass


class Generation(Base):
    __tablename__ = "generations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    modules: Mapped[list["DotfileModule"]] = relationship(
        back_populates="generation",
        cascade="all, delete-orphan",
    )


class DotfileModule(Base):
    __tablename__ = "dotfile_modules"
    __table_args__ = (
        UniqueConstraint("generation_id", "module_name", name="uq_generation_module"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[UUID] = mapped_column(
        ForeignKey("generations.id", ondelete="CASCADE"),
        index=True,
    )
    module_name: Mapped[str] = mapped_column(String(255), index=True)
    output_path: Mapped[Path] = mapped_column(PathType)
    target_path: Mapped[Path] = mapped_column(PathType)

    @validates("module_name")
    def _normalize_module_name(self, key, value):
        return value.strip()

    @validates("output_path", "target_path")
    def _normalize_module_paths(self, key, value):
        return _normalize_path(value)

    def normalized_output_path(self) -> Path:
        return _normalize_path(self.output_path) or self.output_path

    generation: Mapped[Generation] = relationship(back_populates="modules")
    rendered_files: Mapped[list["RenderedFile"]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
    )


class RenderedFile(Base):
    __tablename__ = "rendered_files"
    __table_args__ = (
        UniqueConstraint("module_id", "file_path", name="uq_module_file"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    module_id: Mapped[int] = mapped_column(
        ForeignKey("dotfile_modules.id", ondelete="CASCADE"),
        index=True,
    )
    file_path: Mapped[Path] = mapped_column(PathType)
    template_path: Mapped[Path] = mapped_column(PathType)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)

    @validates("file_path", "template_path")
    def _normalize_paths(self, key, value):
        return _normalize_path(value)

    module: Mapped[DotfileModule] = relationship(back_populates="rendered_files")
