from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware, types
from loguru import logger
from redis.asyncio import Redis

from ..db import update_user_activity


class ActivityMiddleware(BaseMiddleware):
    """Отслеживает и обновляет время последней активности пользователя.

    Использует Redis для дебаунса (не чаще 1 раза в 5 минут на пользователя),
    чтобы исключить лишнюю нагрузку на PostgreSQL при частых запросах.
    """

    def __init__(self, redis: Redis, debounce_seconds: int = 300):
        self.redis = redis
        self.debounce_seconds = max(10, debounce_seconds)

    async def __call__(
        self,
        handler: Callable[[types.TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: types.TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, 'from_user', None)
        if user and not user.is_bot:
            key = f'user:act:{user.id}'
            try:
                # set с nx=True возвращает True, если ключа ещё не было
                should_update = await self.redis.set(
                    key, 1, ex=self.debounce_seconds, nx=True
                )
                if should_update:
                    await update_user_activity(user.id)
            except Exception as e:
                logger.debug(f'Ошибка обновления активности пользователя {user.id}: {e}')

        return await handler(event, data)
