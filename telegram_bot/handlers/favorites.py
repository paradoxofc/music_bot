from contextlib import suppress

from aiogram import Router, F
from aiogram import types
from aiogram.exceptions import TelegramBadRequest
from loguru import logger

from ..db import (
    add_to_favorites as db_add_to_favorites,
    delete_from_favorites as db_delete_from_favorites,
    get_favorites as db_get_favorites,
    send_event,
)
from ..keyboards import get_download_kb, get_favorites_kb, get_main_kb
from ..middlewares import YAMServiceMiddleware
from ..services import YAMService
from ..texts import MAIN_TEXT, NONE_FAVORITES_TEXT
from ..validators import is_valid_track_id

router = Router()
router.callback_query.middleware(YAMServiceMiddleware())


@router.callback_query(lambda c: c.data.startswith('add_to_favorites'))
async def add_to_favorites(cb: types.CallbackQuery, yam_service: YAMService) -> None:
    track_id = cb.data.split(':')[-1]
    if not is_valid_track_id(track_id):
        await cb.answer('Некорректный трек', show_alert=True)
        return

    logger.info(f'Пользователь {cb.from_user.id} добавляет трек {track_id} в избранное')
    track_title, artist_id = await yam_service.get_track_info(track_id)

    await db_add_to_favorites(
        chat_id=cb.from_user.id,
        track_id=track_id,
        title=track_title,
        artist_id=artist_id,
    )
    await send_event(event_type=3, chat_id=cb.from_user.id)
    await cb.message.edit_reply_markup(reply_markup=get_download_kb(track_id, artist_id, True))
    await cb.answer()


@router.callback_query(lambda c: c.data.startswith('delete_from_favorites'))
async def delete_from_favorites(cb: types.CallbackQuery) -> None:
    parts = cb.data.split(':')
    if len(parts) < 3:
        await cb.answer('Некорректные данные', show_alert=True)
        return

    track_id = parts[-2]
    artist_id = parts[-1]
    if not is_valid_track_id(track_id):
        await cb.answer('Некорректный трек', show_alert=True)
        return

    logger.info(f'Пользователь {cb.from_user.id} удаляет трек {track_id} из избранного')

    await db_delete_from_favorites(chat_id=cb.from_user.id, track_id=track_id)
    await cb.message.edit_reply_markup(reply_markup=get_download_kb(track_id, artist_id))
    await cb.answer()


@router.callback_query(lambda c: c.data == 'favorites:close')
async def close_favorites(cb: types.CallbackQuery) -> None:
    """Старые сообщения с кнопкой ❌ — возврат в главное меню без удаления."""
    await cb.answer()
    with suppress(TelegramBadRequest):
        await cb.message.edit_text(text=MAIN_TEXT, reply_markup=get_main_kb())
    with suppress(TelegramBadRequest):
        await cb.message.edit_caption(caption=MAIN_TEXT, reply_markup=get_main_kb())


@router.callback_query(F.data.regexp(r'^favorites:\d+$'))
async def favorites_page(cb: types.CallbackQuery) -> None:
    page = cb.data.split(':')[-1]
    logger.debug(f'Пользователь {cb.from_user.id} открыл избранное — страница {page}')

    favorites = await db_get_favorites(cb.from_user.id, page)
    if not favorites['results']:
        await cb.answer('Больше нет треков', show_alert=True)
        return

    await cb.message.edit_reply_markup(reply_markup=get_favorites_kb(data=favorites))
    await cb.answer()
