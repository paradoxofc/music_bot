from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.types import InlineQueryResultAudio, InlineQueryResultCachedAudio
from loguru import logger

from ..db import get_tracks_by_ids
from ..middlewares import YAMServiceMiddleware
from ..services import YAMService
from ..texts import get_music_caption

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

        artist, real_title, audio_url, cover_url = link_data
        audio_result = InlineQueryResultAudio(
            id=track_id,
            audio_url=audio_url,
            title=real_title,
            performer=artist,
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
        if not search_result or not search_result.get('tracks'):
            logger.info(
                f'Ничего не найдено по inline-запросу: {query_text!r} '
                f'у пользователя {query.from_user.id}'
            )
            await _answer_empty(query)
            return

        tracks = search_result['tracks'][:INLINE_MAX_RESULTS]
        results = await _build_inline_results(tracks, yam_service)

        if not results:
            logger.info(f'Нет результатов для inline-запроса {query_text!r}')
            await _answer_empty(query)
            return

        cached_count = sum(1 for item in results if isinstance(item, InlineQueryResultCachedAudio))
        logger.info(
            f'Inline для {query.from_user.id}: {len(results)} результатов '
            f'({cached_count} из кэша, {len(results) - cached_count} по URL)'
        )
        await query.answer(
            results=results,
            cache_time=120,
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
