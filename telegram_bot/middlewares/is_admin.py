from typing import Callable, Awaitable, Any

from aiogram import BaseMiddleware
from aiogram.types import Message

from ..config import ADMIN_CHAT_ID


class IsAdminMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any]
    ) -> Any:
        if str(event.from_user.id) != ADMIN_CHAT_ID:
            await event.answer("Доступ запрещен")
            return

        return await handler(event, data)
