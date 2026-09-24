"""Scheduler dependencies and service factories."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from functools import lru_cache

from core.config import settings
from core.database import SqlAlchemyUnitOfWork
from core.storage import (
    ObjectStoragePort,
    StorageRetrySyncService,
    create_storage_adapter,
    create_storage_sync_service,
)

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_storage() -> ObjectStoragePort:
    """Return configured ObjectStorage adapter for scheduler."""
    return create_storage_adapter(settings)


def get_uow() -> SqlAlchemyUnitOfWork:
    """Return a new UnitOfWork instance for scheduler transaction boundaries."""
    return SqlAlchemyUnitOfWork()


def get_storage_sync_callback() -> Callable[[str, str, uuid.UUID], None]:
    """Return callback triggered when a local fallback file is successfully synced to S3."""

    def on_synced(old_local_uri: str, new_s3_uri: str, workspace_id: uuid.UUID) -> None:
        try:
            from chat_api.modules.documents.domain.repository import DocumentRepository

            uow = get_uow()
            with uow:
                repo = uow.get_repo(DocumentRepository)
                if repo:
                    repo.update_storage_uri(old_local_uri, new_s3_uri)
                    uow.commit()
                    logger.info(
                        "Updated Document storage_uri in DB: %s -> %s",
                        old_local_uri,
                        new_s3_uri,
                    )
        except Exception as exc:
            logger.warning("Could not update Document record for synced file: %s", exc)

    return on_synced


@lru_cache(maxsize=1)
def get_storage_sync_service() -> StorageRetrySyncService | None:
    """Return configured StorageRetrySyncService if storage adapter has a fallback outbox."""
    storage = get_storage()
    return create_storage_sync_service(storage, settings)


__all__ = [
    "get_storage",
    "get_storage_sync_callback",
    "get_storage_sync_service",
    "get_uow",
]
