from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql import exists

from stash.models import (
    DotfileModule,
    Generation,
    RenderedFile,
)


class BaseRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, instance: Any) -> Any:
        self._session.add(instance)
        self._session.flush()
        return instance

    def delete(self, instance: Any) -> None:
        self._session.delete(instance)


class GenerationRepository(BaseRepository):
    def create(self, description: str | None = None) -> Generation:
        generation = Generation(description=description)
        return self.add(generation)

    def get(self, generation_id: UUID) -> Generation | None:
        return self._session.get(Generation, generation_id)

    def get_all(self) -> list[Generation]:
        stmt = select(Generation).order_by(Generation.created_at.desc())
        return list(self._session.scalars(stmt))

    def get_latest(self) -> Generation | None:
        stmt = select(Generation).order_by(Generation.created_at.desc()).limit(1)
        return self._session.scalars(stmt).first()

    def get_without_modules(
        self, module_repo: "DotfileModuleRepository"
    ) -> list[Generation]:
        stmt = select(Generation).where(
            ~exists(
                select(DotfileModule.id).where(
                    DotfileModule.generation_id == Generation.id
                )
            )
        )
        return list(self._session.scalars(stmt))


class DotfileModuleRepository(BaseRepository):
    def create(
        self,
        generation_id: UUID,
        module_name: str,
        output_path: Path,
        target_path: Path,
    ) -> DotfileModule:
        module = DotfileModule(
            generation_id=generation_id,
            module_name=module_name,
            output_path=output_path,
            target_path=target_path,
        )
        return self.add(module)

    def delete_by_id(self, module_id: int) -> None:
        module = self._session.get(DotfileModule, module_id)
        if module is not None:
            self._session.delete(module)

    def get_all(self) -> list[DotfileModule]:
        stmt = (
            select(DotfileModule)
            .join(Generation)
            .order_by(
                Generation.created_at.desc(),
                DotfileModule.id.desc(),
                DotfileModule.module_name,
            )
        )
        return list(self._session.scalars(stmt))

    def get_by_generation(self, generation_id: UUID) -> list[DotfileModule]:
        stmt = select(DotfileModule).where(DotfileModule.generation_id == generation_id)
        return list(self._session.scalars(stmt))

    def get_by_module_name(
        self, generation_id: UUID, module_name: str
    ) -> DotfileModule | None:
        stmt = select(DotfileModule).where(
            DotfileModule.generation_id == generation_id,
            DotfileModule.module_name == module_name,
        )
        return self._session.scalars(stmt).first()

    def get_latest_by_module_name(self, module_name: str) -> DotfileModule | None:
        stmt = (
            select(DotfileModule)
            .join(Generation)
            .where(DotfileModule.module_name == module_name)
            .order_by(Generation.created_at.desc(), DotfileModule.id.desc())
            .limit(1)
        )
        return self._session.scalars(stmt).first()

    def delete_stale_modules(self) -> list[int]:
        stmt = (
            select(DotfileModule)
            .join(Generation)
            .order_by(
                DotfileModule.module_name,
                Generation.created_at.desc(),
                DotfileModule.id.desc(),
            )
        )
        modules = list(self._session.scalars(stmt))
        deleted: list[int] = []
        latest_ids: set[str] = set()

        for module in modules:
            if module.module_name in latest_ids:
                self._session.delete(module)
                deleted.append(module.id)
                continue
            latest_ids.add(module.module_name)

        if deleted:
            self._session.flush()

        return deleted


class RenderedFileRepository(BaseRepository):
    def create(
        self,
        module_id: int,
        file_path: str,
        template_path: str,
        content_hash: str,
    ) -> RenderedFile:
        rendered_file = RenderedFile(
            module_id=module_id,
            file_path=file_path,
            template_path=template_path,
            content_hash=content_hash,
        )
        return self.add(rendered_file)

    def get_by_module_with_hashes(self, module_id: int) -> dict[Path, str]:
        stmt = select(RenderedFile).where(RenderedFile.module_id == module_id)
        return {
            record.file_path: record.content_hash
            for record in self._session.scalars(stmt)
        }

    def get_by_module(self, module_id: int) -> list[RenderedFile]:
        stmt = select(RenderedFile).where(RenderedFile.module_id == module_id)
        return list(self._session.scalars(stmt))

    def get_by_generation(self, generation_id: UUID) -> Iterable[RenderedFile]:
        stmt = (
            select(RenderedFile)
            .join(DotfileModule)
            .where(DotfileModule.generation_id == generation_id)
        )
        return list(self._session.scalars(stmt))
