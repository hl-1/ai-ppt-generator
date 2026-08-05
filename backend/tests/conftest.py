import pytest

from app.core.db import engine


@pytest.fixture(autouse=True)
async def _reset_async_engine() -> None:
    # 每个用例独立事件循环，用完后释放连接池，避免 asyncpg 绑到旧 loop
    yield
    await engine.dispose()
