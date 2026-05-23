from aiogram import Router, types
from aiogram.types import InlineQueryResultAudio
from loguru import logger

from ..middlewares import YAMServiceMiddleware
from ..services import YAMService
from ..texts import MUSIC_CAPTION_TEXT

router = Router()
router.inline_query.middleware(YAMServiceMiddleware())

@router.inline_query()
async def inline_search(query: types.InlineQuery, yam_service: YAMService) -> None:
    """Inline-режим: выдает пользователю аудиофайлы сразу с caption'ом, полностью в стиле оригинальных vk/ya музыкальных ботов."""
    query_text = (query.query or '').strip()
    if not query_text:
        logger.debug(f'Пустой inline-запрос от пользователя {query.from_user.id}')
        try:
            await query.answer(
                results=[],
                cache_time=1,
                is_personal=True
            )
        except Exception as e:
            logger.warning(f'Не удалось ответить на пустой inline-запрос пользователя {query.from_user.id}: {e}')
        return
    logger.info(f'Пользователь {query.from_user.id} ищет через inline: {query_text!r}')
    try:
        search_result = await yam_service.search(query=query_text, page='0')
        if not search_result or not search_result.get('tracks'):
            logger.info(
                f'Ничего не найдено по inline-запросу: {query_text!r} у пользователя {query.from_user.id}'
            )
            await query.answer(
                results=[],
                cache_time=1,
                is_personal=True
            )
            return
        tracks = search_result['tracks'][:10]
        results = []
        for idx, track in enumerate(tracks):
            try:
                track_id = str(track['id'])
                # Получаем прямой линк через новый метод
                artist, real_title, audio_url, cover_url = await yam_service.get_track_direct_link(track_id)
                audio_result = InlineQueryResultAudio(
                    id=track_id,
                    audio_url=audio_url,
                    title=real_title,
                    performer=artist,
                    caption=MUSIC_CAPTION_TEXT,
                )
                if cover_url:
                    audio_result.thumbnail_url = cover_url
                results.append(audio_result)
                logger.debug(f'Для inline-track {track_id}: готов аудиорезультат')
            except Exception as e:
                logger.warning(f'Не удалось обработать трек с id={track.get("id")}: {e}')
                continue
        if not results:
            logger.info(f'Нет результатов для inline-запроса {query_text!r}')
            await query.answer(
                results=[],
                cache_time=1,
                is_personal=True
            )
            return
        logger.info(f'Отправка {len(results)} аудио inline пользователю {query.from_user.id}')
        await query.answer(
            results=results,
            cache_time=120,
            is_personal=True
        )
    except Exception as e:
        logger.exception(f'Ошибка при inline поиске {query_text!r} от {query.from_user.id}: {e}')
        try:
            await query.answer(
                results=[],
                cache_time=1,
                is_personal=True
            )
        except Exception as send_error:
            logger.warning(f'Не удалось отправить пустой ответ на ошибочный inline-запрос пользователю {query.from_user.id}: {send_error}')

