from aiogram import Router, types
from aiogram.exceptions import TelegramBadRequest
from loguru import logger

from ..config import DEBUG
from ..db import ensure_user
from ..keyboards.main import get_main_kb
from ..keyboards.op import get_op_subscribe_kb
from ..middlewares.mandatory_subscription import (
    get_cached_active_op_setup,
    mark_user_passed,
)
from ..services.op_check import check_user_op_subscription
from ..texts.main import MAIN_TEXT

router = Router()

DEFAULT_OP_MESSAGE = (
    '<b>📌 Подпишитесь на каналы</b>\n\n'
    'Чтобы пользоваться ботом, подпишитесь на указанные каналы и нажмите '
    '<b>«Проверить подписку»</b>.'
)


def _op_prompt_text(setup: dict) -> str:
    return (setup.get('message') or '').strip() or DEFAULT_OP_MESSAGE


async def _show_op_prompt(cb: types.CallbackQuery, setup: dict) -> None:
    try:
        await cb.message.edit_text(
            text=_op_prompt_text(setup),
            reply_markup=get_op_subscribe_kb(setup['channels']),
        )
    except TelegramBadRequest:
        await cb.message.answer(
            text=_op_prompt_text(setup),
            reply_markup=get_op_subscribe_kb(setup['channels']),
        )


@router.callback_query(lambda c: c.data == 'op:check')
async def op_check_subscription(cb: types.CallbackQuery) -> None:
    setup = await get_cached_active_op_setup()
    if DEBUG:
        logger.debug(
            'op:check user_id={} setup={} channels={}',
            cb.from_user.id,
            setup.get('id') if setup else None,
            [ch.get('channel_ref') for ch in (setup or {}).get('channels', [])],
        )
    if not setup or not setup.get('channels'):
        await cb.answer(
            'ОП не включена или каналы не заданы. В админке: 📌 ОП → каналы → ▶️ Включить',
            show_alert=True,
        )
        return

    status = await check_user_op_subscription(cb.bot, cb.from_user.id, setup['channels'])
    if DEBUG:
        logger.debug(
            'op:check user_id={} passed={} not_subscribed={} check_failed={}',
            cb.from_user.id,
            status.passed,
            status.not_subscribed,
            status.check_failed,
        )

    if status.has_config_error:
        await cb.answer(
            'Бот не может проверить канал. Админ: добавьте бота администратором в канал.',
            show_alert=True,
        )
        await _show_op_prompt(cb, setup)
        return

    if not status.passed:
        await cb.answer('Вы ещё не подписались на все каналы', show_alert=True)
        await _show_op_prompt(cb, setup)
        return

    await mark_user_passed(setup.get('id'), cb.from_user.id)
    await ensure_user(cb.from_user, source='op')
    await cb.answer('Подписка подтверждена!', show_alert=True)
    try:
        await cb.message.delete()
    except TelegramBadRequest:
        pass
    await cb.message.answer(text=MAIN_TEXT, reply_markup=get_main_kb())
