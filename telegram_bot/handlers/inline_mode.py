from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.types import (
    InlineQueryResultArticle,
    InlineQueryResultAudio,
    InlineQueryResultCachedAudio,
    InputTextMessageContent,
)
from loguru import logger

from ..constants import MIN_ALBUM_TRACKS
from ..db import get_tracks_by_ids
from ..middlewares import YAMServiceMiddleware
from ..services import YAMService
from ..texts import get_music_caption

_bot_username: str | None = None


async def _get_bot_username(bot) -> str:
    global _bot_username
    if not _bot_username:
        try:
            bot_info = await bot.get_me()
            _bot_username = bot_info.username or 'bot'
        except Exception:
            return 'bot'
    return _bot_username


router = Router()
router.inline_query.middleware(YAMServiceMiddleware())

INLINE_MAX_RESULTS = 10
DIRECT_LINK_CONCURRENCY = 5


async def _answer_empty(query: types.InlineQuery) -> None:
    await query.answer(results=[], cache_time=1, is_personal=True)


async def _build_inline_results(
    tracks: list[dict],
    yam_service: YAMService,
) -> list[InlineQueryResultAudio | InlineQueryResultCachedAudio]:
    track_ids = [str(track['id']) for track in tracks]
    cached_rows = await get_tracks_by_ids(track_ids)
    cached_by_id = {row['track_id']: row for row in cached_rows if row.get('file_id')}

    uncached_ids = [track_id for track_id in track_ids if track_id not in cached_by_id]
    direct_links = await yam_service.get_track_direct_links_parallel(
        uncached_ids,
        concurrency=DIRECT_LINK_CONCURRENCY,
    )

    results: list[InlineQueryResultAudio | InlineQueryResultCachedAudio] = []
    seen_ids: set[str] = set()

    for track in tracks:
        track_id = str(track['id'])
        if track_id in seen_ids:
            continue
        seen_ids.add(track_id)

        cached = cached_by_id.get(track_id)
        if cached:
            results.append(
                InlineQueryResultCachedAudio(
                    id=track_id,
                    audio_file_id=cached['file_id'],
                    title=cached.get('track_title') or track['title'],
                    performer=cached.get('artist_name'),
                    caption=get_music_caption(),
                    parse_mode=ParseMode.HTML,
                )
            )
            logger.debug(f'Inline-track {track_id}: из кэша file_id')
            continue

        link_data = direct_links.get(track_id)
        if not link_data:
            continue

        artist, real_title, audio_url, cover_url, duration = link_data
        audio_result = InlineQueryResultAudio(
            id=track_id,
            audio_url=audio_url,
            title=real_title,
            performer=artist,
            audio_duration=duration or None,
            caption=get_music_caption(),
            parse_mode=ParseMode.HTML,
        )
        if cover_url:
            audio_result.thumbnail_url = cover_url
        results.append(audio_result)
        logger.debug(f'Inline-track {track_id}: прямая ссылка')

    return results


@router.inline_query()
async def inline_search(query: types.InlineQuery, yam_service: YAMService) -> None:
    """Inline-режим: кэшированные file_id + параллельная загрузка ссылок для новых треков."""
    query_text = (query.query or '').strip()
    if not query_text:
        logger.debug(f'Пустой inline-запрос от пользователя {query.from_user.id}')
        try:
            await _answer_empty(query)
        except Exception as e:
            logger.warning(
                f'Не удалось ответить на пустой inline-запрос пользователя {query.from_user.id}: {e}'
            )
        return

    logger.info(f'Пользователь {query.from_user.id} ищет через inline: {query_text!r}')
    try:
        search_result = await yam_service.search(query=query_text, page='0')
        if not search_result or (not search_result.get('tracks') and not search_result.get('albums')):
            logger.info(
                f'Ничего не найдено по inline-запросу: {query_text!r} '
                f'у пользователя {query.from_user.id}'
            )
            await _answer_empty(query)
            return

        tracks = search_result.get('tracks', [])[:INLINE_MAX_RESULTS]
        results = await _build_inline_results(tracks, yam_service) if tracks else []

        # Если найден альбом — ставим его на ПЕРВОЕ место в списке результатов (только от 4 треков)
        albums = [
            a for a in search_result.get('albums', [])
            if a.get('track_count', 0) >= MIN_ALBUM_TRACKS
        ]
        if albums:
            album = albums[0]
            album_id = str(album['id'])
            artist_name = album.get('artist_name') or 'Исполнитель'
            album_title = album.get('title') or 'Альбом'
            track_count = album.get('track_count', 0)
            bot_username = await _get_bot_username(query.bot)

            album_article = InlineQueryResultArticle(
                id=f'album:{album_id}',
                title=f'Альбом: {artist_name} — {album_title}',
                description=f'📥 Скачать весь альбом • {track_count} треков',
                thumbnail_url=album.get('cover_url'),
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f'Альбом: {artist_name} — {album_title}\n'
                        f'Всего треков: {track_count}\n\n'
                        f'Нажмите кнопку ниже, чтобы скачать весь альбом в боте:'
                    ),
                    parse_mode=ParseMode.HTML,
                ),
                reply_markup=types.InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            types.InlineKeyboardButton(
                                text=f'📥 Скачать альбом ({track_count} тр.)',
                                url=f'https://t.me/{bot_username}?start=album_{album_id}',
                            )
                        ]
                    ]
                ),
            )
            results.insert(0, album_article)

        if not results:
            logger.info(f'Нет результатов для inline-запроса {query_text!r}')
            await _answer_empty(query)
            return


        cached_count = sum(1 for item in results if isinstance(item, InlineQueryResultCachedAudio))
        has_direct_links = cached_count < len(results)
        # Прямые ссылки Яндекса живут ~30 сек — кэшировать их дольше бессмысленно:
        # пользователь, выбравший трек через 1 мин, получит 403.
        # Если все треки из кэша (file_id), можно кэшировать дольше.
        cache_time = 25 if has_direct_links else 300
        logger.info(
            f'Inline для {query.from_user.id}: {len(results)} результатов '
            f'({cached_count} из кэша, {len(results) - cached_count} по URL), '
            f'cache_time={cache_time}s'
        )
        await query.answer(
            results=results,
            cache_time=cache_time,
            is_personal=True,
        )
    except Exception as e:
        logger.exception(f'Ошибка при inline поиске {query_text!r} от {query.from_user.id}: {e}')
        try:
            await _answer_empty(query)
        except Exception as send_error:
            logger.warning(
                f'Не удалось отправить пустой ответ на ошибочный inline-запрос '
                f'пользователю {query.from_user.id}: {send_error}'
            )
