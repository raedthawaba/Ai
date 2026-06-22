"""FastAPI Dependencies — حقن التبعيات."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from data_engine.storage.storage_manager import StorageManager

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_storage_manager() -> StorageManager:
    return StorageManager()


async def get_storage_manager() -> StorageManager:
    """Dependency: إرجاع StorageManager المشترك."""
    manager = _get_storage_manager()
    return manager


StorageManagerDep = Annotated[StorageManager, Depends(get_storage_manager)]
