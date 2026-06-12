"""Общие фикстуры для тестов в Docker (см. docker-compose.test.yml)."""

import pytest_asyncio

from telegram_bot import db as db_module


@pytest_asyncio.fixture(scope="session")
async def db_pool():
    pool = await db_module.init_db_pool()
    yield pool
    if db_module._db_pool is not None:
        await db_module._db_pool.close()
        db_module._db_pool = None
