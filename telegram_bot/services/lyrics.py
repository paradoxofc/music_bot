from loguru import logger
from tenacity import retry, stop_after_attempt, wait_fixed
from yandex_music.exceptions import NetworkError

from ..config import YAM_TOKEN


class LyricsService:
    """Сервис для получения текстов песен из Яндекс Музыки."""

    def __init__(self, token: str):
        """Инициализация сервиса."""
        self.token = token

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def get_lyrics(self, track_id: str, client) -> str | None:
        """Получает текст песни по track_id - возвращает только чистый текст (не json, не объект)."""
        try:
            track_list = await client.tracks(track_id)
            if not track_list:
                return None

            track = track_list[0]

            # Пробуем через supplement
            try:
                supplement = await track.get_supplement_async()
                lyrics = None
                if supplement and hasattr(supplement, 'lyrics') and supplement.lyrics:
                    lyr_obj = supplement.lyrics
                    # Поиск приоритетных атрибутов
                    if hasattr(lyr_obj, 'full_lyrics') and lyr_obj.full_lyrics:
                        lyrics = lyr_obj.full_lyrics
                    elif hasattr(lyr_obj, 'lyrics') and lyr_obj.lyrics:
                        lyrics = lyr_obj.lyrics
                    elif hasattr(lyr_obj, 'text') and lyr_obj.text:
                        lyrics = lyr_obj.text
                    else:
                        lyrics = str(lyr_obj)

                # Приводим к строке и чистим от технических полей (id, rights и др.)
                if lyrics:
                    import re
                    # Избавляемся от json/pythonic представлений
                    # Оставляем только сам поэтический текст
                    lyrics = str(lyrics).strip()

                    # Чистим технические поля если они затесались в строку
                    lyrics = re.sub(r"\\n", "\n", lyrics)
                    # Удалить ненужные префиксы (например, {id:123, ...}) если вдруг остались
                    lyrics = re.sub(r"^\{'?id'?\s*:[^,]*,?", '', lyrics)
                    lyrics = re.sub(r"(full_lyrics|lyrics|has_rights|show_translation|text_language|url|')[:=][^,}]*,?", '', lyrics)
                    # Удалить фигурные/квадратные скобки, если они остались
                    lyrics = re.sub(r"[\{\}\[\]]", '', lyrics)
                    # Удалить лишние запятые и отступы подряд
                    lyrics = re.sub(r",\s*\n?", '\n', lyrics)
                    lyrics = re.sub(r"\n{2,}", "\n\n", lyrics) # двойные отступы между куплетами
                    lyrics = lyrics.strip()
                    if lyrics:
                        return lyrics
            except Exception as e:
                logger.debug(f'Не удалось получить текст через supplement: {e}')

            # Через lyrics_id напрямую
            try:
                if hasattr(track, 'lyrics_id') and track.lyrics_id:
                    lyrics_obj = await client.lyrics(track.lyrics_id)
                    lyrics = None
                    # Атрибуты или строка
                    if hasattr(lyrics_obj, 'full_lyrics') and lyrics_obj.full_lyrics:
                        lyrics = lyrics_obj.full_lyrics
                    elif hasattr(lyrics_obj, 'lyrics') and lyrics_obj.lyrics:
                        lyrics = lyrics_obj.lyrics
                    elif hasattr(lyrics_obj, 'text') and lyrics_obj.text:
                        lyrics = lyrics_obj.text
                    else:
                        lyrics = str(lyrics_obj)
                    # Чистка
                    if lyrics:
                        import re
                        lyrics = str(lyrics).strip()
                        lyrics = re.sub(r"\\n", "\n", lyrics)
                        lyrics = re.sub(r"^\{'?id'?\s*:[^,]*,?", '', lyrics)
                        lyrics = re.sub(r"(full_lyrics|lyrics|has_rights|show_translation|text_language|url|')[:=][^,}]*,?", '', lyrics)
                        lyrics = re.sub(r"[\{\}\[\]]", '', lyrics)
                        lyrics = re.sub(r",\s*\n?", '\n', lyrics)
                        lyrics = re.sub(r"\n{2,}", "\n\n", lyrics)
                        lyrics = lyrics.strip()
                        if lyrics:
                            return lyrics
            except Exception as e:
                logger.debug(f'Не удалось получить текст через lyrics_id: {e}')

            return None
        except NetworkError:
            logger.error(f'Network error while getting lyrics for track {track_id}')
            return None
        except Exception as e:
            logger.exception(f'Failed to get lyrics for track {track_id}: {e}')
            return None


def get_lyrics_service() -> LyricsService:
    """Создает и возвращает экземпляр LyricsService."""
    return LyricsService(token=YAM_TOKEN)

