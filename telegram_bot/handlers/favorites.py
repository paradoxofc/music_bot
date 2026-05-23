from aiogram import Router
from aiogram import types
from loguru import logger

from ..db import (
    add_to_favorites as db_add_to_favorites,
    delete_from_favorites as db_delete_from_favorites,
    get_favorites as db_get_favorites,
    send_event,
)
from ..keyboards import get_download_kb, get_favorites_kb
from ..middlewares import YAMServiceMiddleware
from ..services import YAMService
from ..texts import NONE_FAVORITES_TEXT

router = Router()
router.callback_query.middleware(YAMServiceMiddleware())


@router.callback_query(lambda c: c.data.startswith('add_to_favorites'))
async def add_to_favorites(cb: types.CallbackQuery, yam_service: YAMService) -> None:
    track_id = cb.data.split(':')[-1]
    logger.info(f'Пользователь {cb.from_user.id} добавляет трек {track_id} в избранное')
    track_title, artist_id = await yam_service.get_track_info(track_id)

    await db_add_to_favorites(
        chat_id=cb.from_user.id,
        track_id=track_id,
        title=track_title,
        artist_id=artist_id,
    )
    await send_event(event_type=3, chat_id=cb.from_user.id)  # 3 = ADD_TO_FAVORITES
    await cb.message.edit_reply_markup(reply_markup=get_download_kb(track_id, artist_id, True))
    await cb.answer()


@router.callback_query(lambda c: c.data.startswith('delete_from_favorites'))
async def delete_from_favorites(cb: types.CallbackQuery) -> None:
    track_id = cb.data.split(':')[-2]
    artist_id = cb.data.split(':')[-1]
    logger.info(f'Пользователь {cb.from_user.id} удаляет трек {track_id} из избранного')

    await db_delete_from_favorites(chat_id=cb.from_user.id, track_id=track_id)
    await cb.message.edit_reply_markup(reply_markup=get_download_kb(track_id, artist_id))
    await cb.answer()


@router.callback_query(lambda c: c.data.startswith('favorites'))
async def get_favorites(cb: types.CallbackQuery) -> None:
    page = cb.data.split(':')[-1]
    logger.debug(f'Пользователь {cb.from_user.id} открыл избранное — страница {page}')

    favorites = await db_get_favorites(cb.from_user.id, page)
    if not favorites:
        logger.info(f'У пользователя {cb.from_user.id} нет избранного')
        await cb.message.answer(text=NONE_FAVORITES_TEXT)
        return

    # Преобразуем список в формат, который ожидает get_favorites_kb
    favorites_data = {'results': favorites}
    await cb.message.edit_reply_markup(
        reply_markup=get_favorites_kb(data=favorites_data, chat_id=cb.from_user.id)
    )
    await cb.answer()
