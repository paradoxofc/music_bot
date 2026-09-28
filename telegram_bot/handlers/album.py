import asyncio
from contextlib import suppress

from aiogram import Router, types, F
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from loguru import logger

from ..db import get_track, save_track, send_event
from ..constants import EventType
from ..middlewares import YAMServiceMiddleware
from ..services import YAMService
from ..texts import get_music_caption
from ..utils import get_error_kb, show_advert

router = Router()
router.callback_query.middleware(YAMServiceMiddleware())

ALBUM_TRACKS_PAGE_SIZE = 10


def get_album_view_kb(album_id: str, track_count: int) -> types.InlineKeyboardMarkup:
    """Клавиатура карточки альбома."""
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text=f'📥 Скачать все треки ({track_count})',
                    callback_data=f'album:dl:{album_id}',
                )
            ],
            [
                types.InlineKeyboardButton(
                    text='📋 Список треков',
                    callback_data=f'album:tracks:{album_id}:0',
                )
            ],
            [
                types.InlineKeyboardButton(
                    text='◀️ В главное меню',
                    callback_data='main:menu',
                )
            ],
        ]
    )


def get_album_tracks_kb(
    album_id: str,
    tracks: list[dict],
    page: int = 0,
) -> types.InlineKeyboardMarkup:
    """Клавиатура со списком треков альбома и пагинацией."""
    start_idx = page * ALBUM_TRACKS_PAGE_SIZE
    page_tracks = tracks[start_idx : start_idx + ALBUM_TRACKS_PAGE_SIZE]

    keyboard = []
    for track in page_tracks:
        track_id = str(track['id'])
        artist_id = str(track.get('artist_id', '0'))
        title = track.get('title', 'Без названия')
        if len(title) > 45:
            title = title[:44] + '…'
        keyboard.append([
            types.InlineKeyboardButton(
                text=title,
                callback_data=f'download:{track_id}:{artist_id}',
            )
        ])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            types.InlineKeyboardButton(
                text='◀️',
                callback_data=f'album:tracks:{album_id}:{page - 1}',
            )
        )
    if start_idx + ALBUM_TRACKS_PAGE_SIZE < len(tracks):
        nav_buttons.append(
            types.InlineKeyboardButton(
                text='▶️',
                callback_data=f'album:tracks:{album_id}:{page + 1}',
            )
        )
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([
        types.InlineKeyboardButton(
            text=f'📥 Скачать весь альбом ({len(tracks)})',
            callback_data=f'album:dl:{album_id}',
        )
    ])
    keyboard.append([
        types.InlineKeyboardButton(
            text='◀️ Назад к альбому',
            callback_data=f'album:view:{album_id}',
        )
    ])
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def format_album_card_text(album: dict | None = None) -> str:
    return 'Выберите действие'


async def send_album_card(
    message: types.Message,
    album_id: str,
    yam_service: YAMService,
) -> None:
    """Отправляет карточку альбома в чат (используется при inline deep link /start album_id)."""
    album = await yam_service.get_album_with_tracks(album_id)
    if not album:
        await message.answer(
            '❌ Альбом не найден или недоступен.',
            reply_markup=get_error_kb('Альбом не найден или недоступен', context=f'Альбом ID: {album_id}'),
        )
        return

    text = format_album_card_text(album)
    kb = get_album_view_kb(album_id, album.get('track_count', 0))
    await message.answer(text=text, reply_markup=kb)


@router.callback_query(F.data.startswith('album:view:'))
async def album_view_callback(cb: types.CallbackQuery, yam_service: YAMService) -> None:
    """Просмотр карточки альбома."""
    album_id = cb.data.split(':')[-1]
    album = await yam_service.get_album_with_tracks(album_id)
    if not album:
        await cb.answer('Альбом не найден или недоступен', show_alert=True)
        if cb.message:
            await cb.message.answer(
                '❌ Альбом не найден или недоступен.',
                reply_markup=get_error_kb('Альбом не найден или недоступен', context=f'Альбом ID: {album_id}'),
            )
        return

    await cb.answer()
    text = format_album_card_text(album)
    kb = get_album_view_kb(album_id, album.get('track_count', 0))

    if cb.message:
        if cb.message.photo:
            with suppress(TelegramBadRequest):
                await cb.message.delete()
            await cb.message.answer(text=text, reply_markup=kb)
            return

        with suppress(TelegramBadRequest):
            await cb.message.edit_text(
                text=text,
                reply_markup=kb,
            )


@router.callback_query(F.data.startswith('album:tracks:'))
async def album_tracks_callback(cb: types.CallbackQuery, yam_service: YAMService) -> None:
    """Список треков альбома."""
    parts = cb.data.split(':')
    album_id = parts[2]
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0

    album = await yam_service.get_album_with_tracks(album_id)
    if not album or not album.get('tracks'):
        await cb.answer('Треки альбома не найдены', show_alert=True)
        if cb.message:
            await cb.message.answer(
                '❌ Треки альбома не найдены.',
                reply_markup=get_error_kb('Треки альбома не найдены', context=f'Альбом ID: {album_id}'),
            )
        return

    await cb.answer()
    tracks = album['tracks']
    kb = get_album_tracks_kb(album_id, tracks, page=page)
    text = (
        f"📋 <b>Треки альбома</b> «{album.get('title', '')}»\n"
        f"Страница {page + 1} из {(len(tracks) - 1) // ALBUM_TRACKS_PAGE_SIZE + 1}:"
    )

    if cb.message:
        if cb.message.photo:
            with suppress(TelegramBadRequest):
                await cb.message.delete()
            await cb.message.answer(text=text, reply_markup=kb, parse_mode=ParseMode.HTML)
            return

        with suppress(TelegramBadRequest):
            await cb.message.edit_text(text=text, reply_markup=kb, parse_mode=ParseMode.HTML)


@router.callback_query(F.data.startswith('album:dl:'))
async def album_download_all_callback(
    cb: types.CallbackQuery, yam_service: YAMService
) -> None:
    """Скачивание и отправка всех треков альбома."""
    album_id = cb.data.split(':')[-1]
    album = await yam_service.get_album_with_tracks(album_id)
    if not album or not album.get('tracks'):
        await cb.answer('Альбом пуст или недоступен', show_alert=True)
        if cb.message:
            await cb.message.answer(
                '❌ Альбом пуст или недоступен.',
                reply_markup=get_error_kb('Альбом пуст или недоступен', context=f'Альбом ID: {album_id}'),
            )
        return

    tracks = album['tracks']
    total_tracks = len(tracks)
    album_title = album.get('title', 'Альбом')

    await cb.answer('Начинаю отправку альбома...')
    status_msg = await cb.message.answer(
        f'⏳ <b>Загружаю альбом «{album_title}»...</b>\n'
        f'Подготовка треков: 0/{total_tracks}',
        parse_mode=ParseMode.HTML,
    )

    sent_count = 0
    failed_count = 0

    try:
        for idx, track_info in enumerate(tracks, start=1):
            track_id = str(track_info['id'])
            artist_id = str(track_info.get('artist_id', '0'))

            try:
                cached = await get_track(track_id)
                if cached and cached.get('file_id'):
                    # Быстрая отправка из кэша Telegram
                    await cb.bot.send_audio(
                        chat_id=cb.from_user.id,
                        audio=cached['file_id'],
                        performer=cached.get('artist_name'),
                        title=cached.get('track_title') or track_info.get('title'),
                        caption=get_music_caption(),
                        parse_mode=ParseMode.HTML,
                    )
                    sent_count += 1
                else:
                    # Скачивание и сохранение file_id
                    (
                        artist,
                        title,
                        audio_file,
                        cover_file,
                        duration,
                    ) = await yam_service.download_track(track_id)
                    msg = await cb.bot.send_audio(
                        chat_id=cb.from_user.id,
                        audio=audio_file,
                        performer=artist,
                        title=title,
                        thumbnail=cover_file,
                        duration=duration or None,
                        caption=get_music_caption(),
                        parse_mode=ParseMode.HTML,
                    )
                    if msg.audio:
                        await save_track(
                            track_id=track_id,
                            file_id=msg.audio.file_id,
                            artist_id=artist_id,
                            artist_name=artist,
                            track_title=title,
                        )
                    sent_count += 1

            except Exception as e:
                logger.warning(f'Не удалось скачать трек {track_id} из альбома {album_id}: {e}')
                failed_count += 1

            # Обновляем статус каждые 3 трека или на последнем треке
            if idx % 3 == 0 or idx == total_tracks:
                with suppress(Exception):
                    await status_msg.edit_text(
                        f'⏳ <b>Загружаю альбом «{album_title}»...</b>\n'
                        f'Отправлено: <b>{sent_count}/{total_tracks}</b>'
                        + (f' (ошибок: {failed_count})' if failed_count else ''),
                        parse_mode=ParseMode.HTML,
                    )

            await asyncio.sleep(0.5)

        with suppress(Exception):
            await status_msg.delete()

        await send_event(event_type=EventType.DOWNLOAD, chat_id=cb.from_user.id)
        await show_advert(cb.from_user.id)
    except Exception as e:
        logger.exception(f'Ошибка при скачивании альбома {album_id}: {e}')
        with suppress(Exception):
            await status_msg.delete()
        if cb.message:
            await cb.message.answer(
                '❌ Произошла ошибка при загрузке альбома.',
                reply_markup=get_error_kb(e, context=f'Загрузка альбома ID: {album_id}'),
            )
