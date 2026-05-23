from abc import ABC
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, ChosenInlineResult
from loguru import logger

from ..services import get_yam_service


class YAMServiceMiddleware(BaseMiddleware):
    """Мидлварь для добавления сервиса Yandex Music в контекст хендлера."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Логируем все события ChosenInlineResult для отладки
        if isinstance(event, ChosenInlineResult):
            logger.info(
                f'[MIDDLEWARE] ChosenInlineResult получен: '
                f'result_id={event.result_id}, '
                f'user_id={event.from_user.id}, '
                f'inline_message_id={event.inline_message_id}'
            )
        data['yam_service'] = get_yam_service()
        return await handler(event, data)
