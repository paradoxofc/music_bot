from aiogram import BaseMiddleware
from aiogram import types
from redis.asyncio import Redis


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, redis: Redis):
        self.redis = redis
        self.limit = 1
        self.period = 1

    async def __call__(self, handler, event: types.TelegramObject, data: dict):
        user_id = event.from_user.id

        if isinstance(event, types.Message):
            kind = 'msg'
        elif isinstance(event, types.CallbackQuery):
            kind = 'cb'
        else:
            return await handler(event, data)

        key = f'rl:{kind}:{user_id}'

        current = await self.redis.incr(key)
        if current == 1:
            await self.redis.expire(key, self.period)

        if current > self.limit:
            text = '⏳ Пожалуйста, не так быстро 🙂'
            if isinstance(event, types.Message):
                await event.answer(text)
            if isinstance(event, types.CallbackQuery):
                await event.answer(text, show_alert=True)
            return

        return await handler(event, data)
