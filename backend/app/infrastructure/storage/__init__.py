from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.infrastructure.storage.base import Storage


@lru_cache
def get_storage() -> Storage:
    settings = get_settings()
    if settings.storage_driver == "cos":
        from app.infrastructure.storage.cos import CosStorage

        return CosStorage(
            bucket=settings.cos_bucket,
            region=settings.cos_region,
            secret_id=settings.cos_secret_id,
            secret_key=settings.cos_secret_key,
        )

    from app.infrastructure.storage.local import LocalStorage

    return LocalStorage(Path(settings.storage_local_dir))
