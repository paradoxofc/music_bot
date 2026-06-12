from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, InlineQuery, Message, TelegramObject
from loguru import logger

from ..config import DEBUG, admin_user_id
from ..db import ensure_user, get_active_op_setup, get_user
from ..keyboards.op import get_op_subscribe_kb
from ..services.op_check import check_user_op_subscription

DEFAULT_OP_MESSAGE = (
    '<b>📌 Подпишитесь на каналы</b>\n\n'
    'Чтобы пользоваться ботом, подпишитесь на указанные каналы и нажмите '
    '<b>«Проверить подписку»</b>.'
)


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

        admin_id = admin_user_id()
        if admin_id is not None and user.id == admin_id:
            return await handler(event, data)

        if isinstance(event, CallbackQuery) and event.data == 'op:check':
            if DEBUG:
                logger.debug('ОП middleware: пропуск op:check для user_id={}', user.id)
            return await handler(event, data)

        setup = await get_active_op_setup()
        if not setup or not setup.get('channels'):
            if DEBUG:
                logger.debug(
                    'ОП middleware: проверка выключена (setup={}, channels={}) user_id={}',
                    bool(setup),
                    len(setup.get('channels') or []) if setup else 0,
                    user.id,
                )
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
            if await get_user(user.id) is None:
                await ensure_user(user, source='op')
            return await handler(event, data)
        if status.has_config_error:
            logger.error(
                'ОП: бот не может проверить каналы {} — добавьте бота админом',
                status.check_failed,
            )

        text = (setup.get('message') or '').strip() or DEFAULT_OP_MESSAGE
        markup = get_op_subscribe_kb(setup['channels'])

        if isinstance(event, CallbackQuery):
            await event.answer()
            try:
                await event.message.edit_text(text=text, reply_markup=markup)
            except Exception:
                await event.message.answer(text=text, reply_markup=markup)
            return

        if isinstance(event, Message):
            await event.answer(text=text, reply_markup=markup)
            return

        if isinstance(event, InlineQuery):
            await event.answer(
                results=[],
                cache_time=5,
                switch_pm_text='Подпишитесь на каналы',
                switch_pm_parameter='start',
            )
            return

        return
