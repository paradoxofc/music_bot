from contextlib import suppress
from aiogram import Router, F, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from ...config import is_admin
from ...keyboards import get_admin_main_kb
from ...texts import ADMIN_MAIN_TEXT

router = Router()


@router.callback_query(F.data == 'admin')
async def admin_menu(cb: types.CallbackQuery, state: FSMContext) -> None:
    """Главное меню админки."""
    if not is_admin(cb.from_user.id):
        await cb.answer('Нет доступа', show_alert=True)
        return
    await cb.answer()
    await state.clear()

    text = ADMIN_MAIN_TEXT.format(name=cb.from_user.full_name)
    markup = get_admin_main_kb()

    message = cb.message
    if not isinstance(message, types.Message) or not message.text:
        if isinstance(message, types.Message):
            with suppress(TelegramBadRequest):
                await message.delete()
        await cb.bot.send_message(
            chat_id=cb.from_user.id,
            text=text,
            reply_markup=markup,
        )
        return

    try:
        await message.edit_text(text=text, reply_markup=markup)
    except TelegramBadRequest as e:
        if 'message is not modified' in str(e).lower():
            return
        with suppress(TelegramBadRequest):
            await message.delete()
        await cb.bot.send_message(
            chat_id=cb.from_user.id,
            text=text,
            reply_markup=markup,
        )


@router.message(Command('admin'))
async def admin_command(msg: types.Message, state: FSMContext) -> None:
    """Команда /admin для входа в панель управления."""
    if not is_admin(msg.from_user.id):
        return
    await state.clear()
    await msg.answer(
        text=ADMIN_MAIN_TEXT.format(name=msg.from_user.full_name),
        reply_markup=get_admin_main_kb(),
    )

