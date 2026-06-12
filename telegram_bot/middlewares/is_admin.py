from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from ..config import admin_user_id


class IsAdminMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, 'from_user', None)
        admin_id = admin_user_id()

        if not user or admin_id is None or user.id != admin_id:
            deny_msg = 'Доступ запрещен'
            if isinstance(event, CallbackQuery):
                await event.answer(deny_msg, show_alert=True)
            elif isinstance(event, Message):
                await event.answer(deny_msg)
            return

        return await handler(event, data)
