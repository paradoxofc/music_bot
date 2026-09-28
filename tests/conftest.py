"""Общие фикстуры для тестов в Docker (см. docker-compose.test.yml)."""

import pytest_asyncio

from telegram_bot import db as db_module


@pytest_asyncio.fixture
async def db_pool():
    db_module._db_pool = None
    pool = await db_module.init_db_pool()
    yield pool
    await db_module.close_db_pool()
