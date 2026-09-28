from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram import types
from loguru import logger
from redis.asyncio import Redis
from redis.exceptions import RedisError

from ..config import THROTTLE_INLINE_LIMIT, THROTTLE_MESSAGE_LIMIT, THROTTLE_PERIOD

THROTTLE_TEXT = '⏳ Пожалуйста, не так быстро 🙂'


class ThrottlingMiddleware(BaseMiddleware):
    """Ограничивает частоту событий от одного пользователя.

    Работает «fail-open»: если Redis недоступен, апдейт всё равно
    обрабатывается, иначе бот полностью ложится вместе с кэшем.
    """

    def __init__(
        self,
        redis: Redis,
        limit: int = THROTTLE_MESSAGE_LIMIT,
        period: int = THROTTLE_PERIOD,
        inline_limit: int = THROTTLE_INLINE_LIMIT,
    ):
        self.redis = redis
        self.limit = max(1, limit)
        self.period = max(1, period)
        self.inline_limit = max(1, inline_limit)

    def _describe(self, event: types.TelegramObject) -> tuple[str, int] | None:
        if isinstance(event, types.Message):
            return 'msg', self.limit
        if isinstance(event, types.CallbackQuery):
            return 'cb', self.limit
        if isinstance(event, types.InlineQuery):
            return 'inline', self.inline_limit
        return None

    async def _hit(self, key: str) -> int | None:
        """Возвращает счётчик за окно или None, если Redis недоступен."""
        try:
            current = await self.redis.incr(key)
            if current == 1:
                await self.redis.expire(key, self.period)
            return int(current)
        except RedisError as e:
            logger.warning(f'Троттлинг отключён — Redis недоступен: {e}')
            return None

    async def _should_notify(self, key: str) -> bool:
        """Предупреждаем один раз за окно, чтобы не спамить в ответ на спам."""
        try:
            return bool(await self.redis.set(f'{key}:notified', 1, ex=self.period, nx=True))
        except RedisError:
            return False

    async def __call__(
        self,
        handler: Callable[[types.TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: types.TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        described = self._describe(event)
        user = getattr(event, 'from_user', None)
        if described is None or user is None:
            return await handler(event, data)

        kind, limit = described
        key = f'rl:{kind}:{user.id}'

        current = await self._hit(key)
        if current is None or current <= limit:
            return await handler(event, data)

        if isinstance(event, types.InlineQuery):
            # Inline-запросы нельзя «не ответить» — отдаём пустой результат.
            await event.answer(results=[], cache_time=1, is_personal=True)
            return

        if not await self._should_notify(key):
            return

        if isinstance(event, types.Message):
            await event.answer(THROTTLE_TEXT)
        elif isinstance(event, types.CallbackQuery):
            await event.answer(THROTTLE_TEXT, show_alert=True)
        return
