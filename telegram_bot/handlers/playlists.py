from aiogram import Router, types
from aiogram.utils.media_group import MediaGroupBuilder
from loguru import logger
from yandex_music import TrackShort

from ..constants import MAX_TG_UPLOAD
from ..middlewares import YAMServiceMiddleware
from ..services import YAMService
from ..utils import show_advert

router = Router()
router.callback_query.middleware(YAMServiceMiddleware())


@router.callback_query(lambda c: c.data.startswith('playlist'))
async def get_playlist_tracks(cb: types.CallbackQuery, yam_service: YAMService) -> None:
    playlist_id = cb.data.split(':')[-1]
    logger.info(f'Пользователь {cb.from_user.id} скачивает плейлист {playlist_id}')
    try:
        tracks: list[TrackShort] = await yam_service.get_playlist_tracks(playlist_id)
        await cb.answer('Скачиваю треки...')

        media_group = MediaGroupBuilder()

        await cb.bot.send_chat_action(chat_id=cb.from_user.id, action='upload_document')
        kept_tracks: list[TrackShort] = []
        for track in tracks:
            artist, title, audio, cover = await yam_service.download_track(track.id)
            if len(audio.data) > MAX_TG_UPLOAD:
                logger.info(f'Пропускаю трек {track.id}: файл слишком большой')
                continue
            media_group.add_audio(media=audio, performer=artist, title=title, thumbnail=cover)
            kept_tracks.append(track)

        if not kept_tracks:
            await cb.message.answer('Все треки в подборке слишком большие для отправки.')
            return

        messages = await cb.bot.send_media_group(chat_id=cb.from_user.id, media=media_group.build())
        await show_advert(cb.from_user.id)

        # Сохранение треков в backend отключено
    except Exception as e:
        logger.exception(
            f'Ошибка при скачивании плейлиста {playlist_id} для пользователя {cb.from_user.id}: {e}'
        )
        await cb.message.answer('Не удалось скачать плейлист. Попробуйте позже.')
