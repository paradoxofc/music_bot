from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext

from ...config import admin_user_id
from ...keyboards import get_admin_main_kb
from ...middlewares import IsAdminMiddleware
from ...texts import ADMIN_MAIN_TEXT

router = Router()
router.message.middleware(IsAdminMiddleware())
router.callback_query.middleware(IsAdminMiddleware())


@router.message(F.text.lower().in_(('ap', 'ап',)))
@router.callback_query(lambda c: c.data == 'admin')
async def main(event: types.Message | types.CallbackQuery, state: FSMContext) -> None:
    admin_id = admin_user_id()
    if admin_id is None or event.from_user.id != admin_id:
        return

    await state.clear()
    text = ADMIN_MAIN_TEXT.format(name=event.from_user.full_name)
    markup = get_admin_main_kb()

    if isinstance(event, types.CallbackQuery):
        await event.answer()
        msg = event.message
        if msg.text:
            await msg.edit_text(text=text, reply_markup=markup)
        else:
            await msg.delete()
            await event.bot.send_message(
                chat_id=msg.chat.id,
                text=text,
                reply_markup=markup,
            )
        return

    await event.answer(text=text, reply_markup=markup)
