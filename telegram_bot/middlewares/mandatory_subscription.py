import json
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import (
    CallbackQuery,
    InlineQuery,
    InlineQueryResultsButton,
    Message,
    TelegramObject,
)
from loguru import logger
from redis.exceptions import RedisError

from ..config import (
    DEBUG,
    OP_FAIL_OPEN,
    OP_SETUP_CACHE_TTL,
    OP_USER_CACHE_TTL,
    is_admin,
    redis,
)
from ..db import ensure_user, get_active_op_setup
from ..keyboards.op import get_op_subscribe_kb
from ..services.op_check import check_user_op_subscription

DEFAULT_OP_MESSAGE = (
    '<b>📌 Подпишитесь на каналы</b>\n\n'
    'Чтобы пользоваться ботом, подпишитесь на указанные каналы и нажмите '
    '<b>«Проверить подписку»</b>.'
)

OP_SETUP_CACHE_KEY = 'op:active_setup'
OP_USER_CACHE_PREFIX = 'op:passed:'


async def get_cached_active_op_setup() -> dict | None:
    """Активная ОП с коротким кэшем в Redis.

    Без кэша каждый апдейт делал два запроса в PostgreSQL — на нагрузке это
    самое узкое место бота.
    """
    try:
        cached = await redis.get(OP_SETUP_CACHE_KEY)
        if cached is not None:
            return json.loads(cached) or None
    except (RedisError, ValueError):
        pass

    setup = await get_active_op_setup()
    try:
        await redis.set(
            OP_SETUP_CACHE_KEY,
            json.dumps(setup or {}, ensure_ascii=False, default=str),
            ex=OP_SETUP_CACHE_TTL,
        )
    except RedisError:
        pass
    return setup


async def invalidate_op_cache() -> None:
    """Сбрасывает кэш ОП — вызывать после изменений в админке."""
    try:
        await redis.delete(OP_SETUP_CACHE_KEY)
        async for key in redis.scan_iter(match=f'{OP_USER_CACHE_PREFIX}*', count=500):
            await redis.delete(key)
    except RedisError as e:
        logger.warning(f'Не удалось сбросить кэш ОП: {e}')


async def mark_user_passed(setup_id: Any, user_id: int) -> None:
    try:
        await redis.set(
            f'{OP_USER_CACHE_PREFIX}{setup_id}:{user_id}', 1, ex=OP_USER_CACHE_TTL
        )
    except RedisError:
        pass


async def _user_passed_cached(setup_id: Any, user_id: int) -> bool:
    try:
        return bool(await redis.exists(f'{OP_USER_CACHE_PREFIX}{setup_id}:{user_id}'))
    except RedisError:
        return False


class MandatorySubscriptionMiddleware(BaseMiddleware):
    """Блокирует действия, пока пользователь не подписан на каналы активной ОП."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, 'from_user', None)
        if not user:
            return await handler(event, data)

        if is_admin(user.id):
            return await handler(event, data)

        if isinstance(event, CallbackQuery) and event.data == 'op:check':
            if DEBUG:
                logger.debug('ОП middleware: пропуск op:check для user_id={}', user.id)
            return await handler(event, data)

        setup = await get_cached_active_op_setup()
        if not setup or not setup.get('channels'):
            return await handler(event, data)

        # Подписка уже подтверждалась недавно — не дёргаем Telegram API на каждый апдейт.
        if await _user_passed_cached(setup.get('id'), user.id):
            return await handler(event, data)

        bot = data.get('bot')
        if bot is None:
            if DEBUG:
                logger.warning('ОП middleware: bot отсутствует в data для user_id={}', user.id)
            return await handler(event, data)

        status = await check_user_op_subscription(bot, user.id, setup['channels'])
        if DEBUG:
            logger.debug(
                'ОП middleware: user_id={} setup_id={} passed={} not_sub={} failed={}',
                user.id,
                setup.get('id'),
                status.passed,
                status.not_subscribed,
                status.check_failed,
            )

        if status.passed:
            await mark_user_passed(setup.get('id'), user.id)
            await ensure_user(user, source='op')
            return await handler(event, data)

        if status.has_config_error:
            logger.error(
                'ОП: бот не может проверить каналы {} — добавьте бота админом',
                status.check_failed,
            )
            # Ошибка настройки не должна полностью блокировать бота всем
            # пользователям: при OP_FAIL_OPEN=True пропускаем дальше.
            if OP_FAIL_OPEN and not status.not_subscribed:
                return await handler(event, data)

        text = (setup.get('message') or '').strip() or DEFAULT_OP_MESSAGE
        markup = get_op_subscribe_kb(setup['channels'])

        if isinstance(event, CallbackQuery):
            await event.answer()
            if event.message is None:
                # Сообщение из inline-режима — редактировать нечего.
                return
            try:
                await event.message.edit_text(text=text, reply_markup=markup)
            except Exception:
                try:
                    await event.message.answer(text=text, reply_markup=markup)
                except Exception as e:
                    logger.warning(f'ОП: не удалось показать окно подписки: {e}')
            return

        if isinstance(event, Message):
            await event.answer(text=text, reply_markup=markup)
            return

        if isinstance(event, InlineQuery):
            # switch_pm_text/switch_pm_parameter удалены в Bot API 7.0,
            # вместо них используется параметр button.
            await event.answer(
                results=[],
                cache_time=5,
                is_personal=True,
                button=InlineQueryResultsButton(
                    text='Подпишитесь на каналы',
                    start_parameter='op',
                ),
            )
            return

        return
