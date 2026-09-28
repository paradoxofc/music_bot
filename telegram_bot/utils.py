import sys
import traceback
import uuid
from datetime import datetime
from loguru import logger
from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup

from .config import GRAMADS_ON, redis
from .constants import EventType
from .db import send_event

QUERY_TOKEN_PREFIX = 'query_token:'
QUERY_TOKEN_TTL = 86400  # 24 часа
_local_query_cache: dict[str, str] = {}


def format_error_log(
    error: Exception | str,
    context: str | None = None,
) -> str:
    """Форматирует лог ошибки для буфера обмена."""
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    lines = []
    if isinstance(error, BaseException):
        lines.append(f'[{now_str}] {type(error).__name__}: {error}')
        if context:
            lines.append(f'Контекст: {context}')
        tb = ''.join(traceback.format_exception(type(error), error, error.__traceback__)).strip()
        if tb and tb != 'NoneType: None':
            lines.append(f'\nТрассировка:\n{tb}')
    else:
        lines.append(f'[{now_str}] Ошибка: {error}')
        if context:
            lines.append(f'Контекст: {context}')
        _, exc_val, exc_tb = sys.exc_info()
        if exc_val is not None:
            tb = ''.join(traceback.format_exception(type(exc_val), exc_val, exc_tb)).strip()
            if tb and tb != 'NoneType: None':
                lines.append(f'\nТрассировка:\n{tb}')

    log_text = '\n'.join(lines)
    # Лимит текста Telegram CopyTextButton составляет 4096 символов
    if len(log_text) > 4000:
        log_text = log_text[:3990] + '\n[...сокращено]'
    return log_text


def get_error_kb(
    error: Exception | str,
    context: str | None = None,
    button_text: str = '📋 Скопировать лог',
) -> InlineKeyboardMarkup:
    """Создаёт инлайн-клавиатуру с кнопкой копирования лога ошибки в буфер обмена."""
    log_text = format_error_log(error, context)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=button_text,
                    copy_text=CopyTextButton(text=log_text),
                )
            ]
        ]
    )


async def show_advert(chat_id: int):
    """Показывает рекламу пользователю (Gramads)."""
    if not GRAMADS_ON:
        return
    await send_event(event_type=EventType.SHOW_AD, chat_id=chat_id)


async def remember_query(query: str) -> str:
    """Сохраняет поисковый запрос в Redis под коротким токеном для пагинации (callback_data)."""
    token = uuid.uuid4().hex[:12]
    _local_query_cache[token] = query
    if len(_local_query_cache) > 1000:
        _local_query_cache.pop(next(iter(_local_query_cache)), None)

    key = f'{QUERY_TOKEN_PREFIX}{token}'
    try:
        await redis.set(key, query, ex=QUERY_TOKEN_TTL)
    except Exception as e:
        logger.warning(f'Не удалось сохранить запрос в Redis: {e}')

    return token


async def resolve_query(token: str) -> str | None:
    """Получает сохранённый поисковый запрос по токену."""
    key = f'{QUERY_TOKEN_PREFIX}{token}'
    try:
        query = await redis.get(key)
        if query:
            return query
    except Exception as e:
        logger.warning(f'Не удалось получить запрос из Redis: {e}')

    return _local_query_cache.get(token)

