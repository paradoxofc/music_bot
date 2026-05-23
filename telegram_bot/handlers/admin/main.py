from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext

from ...config import ADMIN_CHAT_ID
from ...keyboards import get_admin_main_kb
from ...middlewares import IsAdminMiddleware
from ...texts import ADMIN_MAIN_TEXT

router = Router()
router.message.middleware(IsAdminMiddleware())
router.callback_query.middleware(IsAdminMiddleware())


@router.message(F.text.lower().in_(('админка', 'админ', 'а')) & F.from_user.id == int(ADMIN_CHAT_ID))
@router.callback_query(lambda c: c.data == 'admin')
async def main(event: types.Message | types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(event, types.CallbackQuery):
        method = event.message.edit_text
        await event.answer()
    else:
        method = event.answer

    await method(
        text=ADMIN_MAIN_TEXT.format(name=event.from_user.full_name),
        reply_markup=get_admin_main_kb()
    )
