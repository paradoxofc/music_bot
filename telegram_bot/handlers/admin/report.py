import asyncio

from aiogram import types
from aiogram.types import BufferedInputFile
from loguru import logger

from .main import router
from ...db import get_all_users_for_report, get_downloads_total_count, get_users_count
from ...keyboards import get_admin_main_kb
from ...services.report_excel import build_users_report_xlsx, report_filename
from ...texts import REPORT_READY_TEXT, REPORT_EMPTY_TEXT

REPORT_KB = types.InlineKeyboardMarkup(
    inline_keyboard=[
        [types.InlineKeyboardButton(text='📥 Скачать Excel', callback_data='admin:report:download')],
        [types.InlineKeyboardButton(text='< Назад', callback_data='admin')],
    ]
)


@router.callback_query(lambda c: c.data == 'admin:report')
async def report_menu(cb: types.CallbackQuery) -> None:
    await cb.answer()
    users_count, downloads_total = await asyncio.gather(
        get_users_count(),
        get_downloads_total_count(),
    )
    text = REPORT_READY_TEXT.format(
        users_count=users_count,
        downloads_total=downloads_total,
    )

    if cb.message.photo or cb.message.document:
        await cb.message.delete()
        await cb.bot.send_message(
            chat_id=cb.message.chat.id,
            text=text,
            reply_markup=REPORT_KB,
        )
        return

    await cb.message.edit_text(text=text, reply_markup=REPORT_KB)


@router.callback_query(lambda c: c.data == 'admin:report:download')
async def report_download(cb: types.CallbackQuery) -> None:
    await cb.answer('Формирую отчёт…')
    users = await get_all_users_for_report()
    if not users:
        await cb.answer(REPORT_EMPTY_TEXT, show_alert=True)
        return

    try:
        buf = await asyncio.to_thread(build_users_report_xlsx, users)
        downloads_total = await get_downloads_total_count()
        document = BufferedInputFile(buf.read(), filename=report_filename())
        await cb.message.answer_document(
            document=document,
            caption=(
                f'📋 Отчёт: {len(users)} пользователей, '
                f'скачано треков: {downloads_total}'
            ),
            reply_markup=REPORT_KB,
        )
        logger.info(f'Админ {cb.from_user.id} скачал отчёт ({len(users)} пользователей)')
    except Exception:
        logger.exception('Ошибка при формировании Excel-отчёта')
        await cb.answer('Не удалось сформировать отчёт', show_alert=True)
