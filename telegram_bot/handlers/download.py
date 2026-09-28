import asyncio
import html

from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from loguru import logger

from ..db import send_event, get_track, save_track, check_favorite
from ..constants import EventType, MAX_TG_UPLOAD
from ..config import LYRICS_REQUEST_URL
from ..keyboards import get_download_kb, get_lyrics_not_found_kb
from ..middlewares import YAMServiceMiddleware
from ..services import YAMService, get_lyrics_service, TrackNotFoundError, TrackTooLargeError
from ..texts import get_bot_link, get_music_caption
from ..utils import get_error_kb, show_advert
from ..validators import is_valid_track_id

router = Router()
router.callback_query.middleware(YAMServiceMiddleware())


async def _keep_upload_action(bot, chat_id: int, stop_event: asyncio.Event) -> None:
    """Повторяет индикатор upload_document каждые 4 сек, пока загрузка не завершилась.

    Без этого индикатор Telegram пропадает через ~5 сек, а загрузка трека может длиться 15–30 сек.
    """
    while not stop_event.is_set():
        try:
            await bot.send_chat_action(chat_id=chat_id, action='upload_document')
        except Exception:
            pass
        # Ждём 4 сек или выходим по stop_event
        with asyncio.timeout(4):
            try:
                await asyncio.shield(stop_event.wait())
            except (asyncio.TimeoutError, Exception):
                pass



@router.callback_query(lambda cb: cb.data.startswith('download'))
async def download_track(cb: types.CallbackQuery, yam_service: YAMService) -> None:
    """Обработчик для скачивания треков."""
    logger.info(f'Пользователь {cb.from_user.id} инициировал скачивание: {cb.data!r}')
    parts = cb.data.split(':')
    if len(parts) < 3:
        await cb.answer('Некорректные данные', show_alert=True)
        return

    track_id = parts[-2]
    artist_id = parts[-1]
    if not is_valid_track_id(track_id) or not is_valid_track_id(artist_id):
        await cb.answer('Некорректный трек', show_alert=True)
        return

    await send_event(event_type=EventType.DOWNLOAD, chat_id=cb.from_user.id)
    await cb.answer('Скачиваю трек...')

    # Запускаем keep-alive задачу: индикатор загрузки будет повторяться пока не скачается трек.
    stop_event = asyncio.Event()
    action_task = asyncio.create_task(
        _keep_upload_action(cb.bot, cb.from_user.id, stop_event)
    )

    try:
        is_favorite = await check_favorite(cb.from_user.id, track_id)
        cached_track = await get_track(track_id)
        if cached_track and (file_id := cached_track.get('file_id', None)):
            try:
                await cb.message.answer_audio(
                    audio=file_id,
                    reply_markup=get_download_kb(track_id, artist_id, is_favorite),
                    caption=get_music_caption(),
                    parse_mode=ParseMode.HTML,
                )
                await show_advert(cb.from_user.id)
                return
            except TelegramBadRequest as e:
                logger.info(f'file_id недействителен у трека {track_id}: {e}')

        artist, title, audio, cover, duration = await yam_service.download_track(track_id)
        if len(audio.data) > MAX_TG_UPLOAD:
            await cb.message.answer(
                '❌ Файл трека слишком большой для отправки.',
                reply_markup=get_error_kb('Файл трека превышает лимит Telegram (50 МБ)', context=f'Трек {track_id}'),
            )
            return
        msg = await cb.message.answer_audio(
            audio=audio,
            performer=artist,
            title=title,
            duration=duration or None,
            thumbnail=cover,
            reply_markup=get_download_kb(track_id, artist_id, is_favorite),
            caption=get_music_caption(),
            parse_mode=ParseMode.HTML,
        )
        await save_track(
            track_id=track_id,
            file_id=msg.audio.file_id,
            artist_id=artist_id,
            artist_name=artist,
            track_title=title,
        )
        await show_advert(cb.from_user.id)
    except TrackNotFoundError as e:
        logger.info(f'Трек {track_id} недоступен для пользователя {cb.from_user.id}')
        await cb.message.answer(
            '❌ Трек недоступен или был удалён.',
            reply_markup=get_error_kb(e, context=f'Трек ID: {track_id}'),
        )
    except TrackTooLargeError as e:
        logger.info(f'Трек {track_id} слишком большой для пользователя {cb.from_user.id}')
        await cb.message.answer(
            '❌ Файл слишком большой для отправки через Telegram (>50 МБ).',
            reply_markup=get_error_kb(e, context=f'Трек ID: {track_id}'),
        )
    except Exception as e:
        logger.exception(
            f'Ошибка при скачивании трека {track_id} для пользователя {cb.from_user.id}'
        )
        await cb.message.answer(
            '❌ Не удалось скачать трек. Попробуйте позже.',
            reply_markup=get_error_kb(e, context=f'Скачивание трека ID: {track_id}'),
        )
    finally:
        stop_event.set()
        action_task.cancel()



@router.callback_query(lambda cb: cb.data.startswith('get_lyrics'))
async def get_lyrics(cb: types.CallbackQuery, yam_service: YAMService) -> None:
    """Обработчик для получения текста песни."""
    logger.info(f'Пользователь {cb.from_user.id} запросил текст песни: {cb.data!r}')
    await cb.answer('Ищу текст песни...')

    track_id = cb.data.split(':')[-1]
    if not is_valid_track_id(track_id):
        await cb.answer('Некорректный трек', show_alert=True)
        return

    try:
        # Получаем информацию о треке для отображения названия
        track_info = await yam_service.get_track_info(track_id)
        track_name = track_info[0]

        # Получаем сервис для получения текстов
        lyrics_service = get_lyrics_service()

        # Получаем текст песни
        lyrics = await lyrics_service.get_lyrics(track_id, yam_service.client)
        if lyrics:
            max_length = 4000
            if len(lyrics) > max_length:
                lyrics = lyrics[:max_length] + '\n\n... (текст обрезан)'
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text='❌', callback_data='delete_lyrics')]]
            )
            bot_link = html.escape(get_bot_link(), quote=True)
            safe_lyrics = html.escape(lyrics)
            response_text = f'{safe_lyrics}\n\n<a href="{bot_link}">Все текста — в одном боте</a>'
            await cb.message.answer(
                text=response_text,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
        else:
            safe_name = html.escape(track_name)
            await cb.message.answer(
                text=f'😔 К сожалению, текст песни «{safe_name}» не найден.',
                reply_markup=get_lyrics_not_found_kb(LYRICS_REQUEST_URL),
            )
    except Exception as e:
        logger.exception(
            f'Ошибка при получении текста песни {track_id} для пользователя {cb.from_user.id}'
        )
        await cb.message.answer(
            '❌ Не удалось получить текст песни. Попробуйте позже.',
            reply_markup=get_error_kb(e, context=f'Текст песни ID: {track_id}'),
        )


@router.callback_query(lambda cb: cb.data == 'delete_lyrics')
async def delete_lyrics_message(cb: types.CallbackQuery):
    """Удаляет сообщение с текстом песни."""
    await cb.message.delete()
    await cb.answer()
