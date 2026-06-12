"""Базовые проверки инфраструктуры. Добавляйте сюда и новые тесты функций."""

import pytest

from telegram_bot.config import redis


@pytest.mark.asyncio
async def test_postgres_select_one(db_pool):
    async with db_pool.acquire() as conn:
        value = await conn.fetchval("SELECT 1")
    assert value == 1


@pytest.mark.asyncio
async def test_redis_ping():
    assert await redis.ping() is True
