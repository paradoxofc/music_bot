from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import KICKED, MEMBER, ChatMemberUpdatedFilter, Command
from aiogram.types import ChatMemberUpdated
from loguru import logger

from ..db import set_blocked_status

router = Router()


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED))
async def user_blocked_bot(event: ChatMemberUpdated) -> None:
    """Деактивирует пользователя, если он заблокировал бота."""
    logger.info(f'Пользователь {event.from_user.id} заблокировал бота')
    await set_blocked_status(chat_id=event.from_user.id, is_blocked=True)


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def user_unblocked_bot(event: ChatMemberUpdated) -> None:
    """Активирует пользователя, если он разблокировал бота."""
    logger.info(f'Пользователь {event.from_user.id} разблокировал бота')
    await set_blocked_status(chat_id=event.from_user.id, is_blocked=False)


@router.callback_query(lambda c: c.data == 'delete_message')
async def delete_message(cb: types.CallbackQuery) -> None:
    logger.debug(f'Удаляем сообщение по запросу пользователя {cb.from_user.id}')
    try:
        await cb.message.delete()
        await cb.answer()
    except TelegramBadRequest:
        await cb.answer('Не удалось удалить сообщение.')


@router.message(Command('donate'))
async def donate_stars(msg: types.Message) -> None:
    logger.info(f'Пользователь {msg.from_user.id} вызвал /donate: {msg.text!r}')
    amount = msg.text.split()[-1]
    if not amount.isdigit():
        await msg.answer('Введите <b>/donate {сумма}</b>')
        return
    await msg.answer_invoice(
        title='Поддержка бота через Stars',
        description='Вы поможете развитию функционала, стабильности и новым возможностям проекта.',
        payload='donate',
        currency='XTR',
        prices=[types.LabeledPrice(label='XTR', amount=int(amount))],
    )


@router.pre_checkout_query()
async def on_pre_checkout_query(query: types.PreCheckoutQuery) -> None:
    logger.debug(f'Подтверждение оплаты от {query.from_user.id}')
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(msg: types.Message) -> None:
    logger.info(f'Пользователь {msg.from_user.id} успешно оплатил поддержку')
    await msg.answer('Спасибо за поддержку! 🤝\nЭто поможет развитию бота.')
