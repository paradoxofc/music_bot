import re

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_fixed
from yandex_music.exceptions import NetworkError, NotFoundError, UnauthorizedError

from ..config import YAM_TOKEN

_LRC_LINE_RE = re.compile(r'^\[\d{1,2}:\d{2}(?:\.\d{2,3})?\]\s*')


def _lrc_to_text(raw: str) -> str:
    """Убирает временные метки LRC, оставляя только строки текста."""
    lines: list[str] = []
    for line in raw.splitlines():
        cleaned = _LRC_LINE_RE.sub('', line).strip()
        if cleaned:
            lines.append(cleaned)
    return '\n'.join(lines)


def _normalize_lyrics(text: str) -> str:
    text = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    return re.sub(r'\n{3,}', '\n\n', text)


class LyricsService:
    """Сервис для получения текстов песен из Яндекс Музыки."""

    def __init__(self, token: str):
        self.token = token

    async def _fetch_by_format(self, client, track_id: str, lyrics_format: str) -> str | None:
        """Запрашивает текст через актуальный API /tracks/{id}/lyrics."""
        lyrics_meta = await client.tracks_lyrics(track_id, format_=lyrics_format)
        if not lyrics_meta:
            return None

        raw = await lyrics_meta.fetch_lyrics_async()
        if not raw or not raw.strip():
            return None

        text = _lrc_to_text(raw) if lyrics_format == 'LRC' else raw
        text = _normalize_lyrics(text)
        return text or None

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def get_lyrics(self, track_id: str, client) -> str | None:
        """Получает текст песни по track_id."""
        try:
            for lyrics_format in ('TEXT', 'LRC'):
                try:
                    text = await self._fetch_by_format(client, track_id, lyrics_format)
                    if text:
                        return text
                except NotFoundError:
                    logger.debug(
                        f'Текст трека {track_id} не найден через API (format={lyrics_format})'
                    )

            return None
        except UnauthorizedError:
            logger.error(f'Нет авторизации для получения текста трека {track_id}')
            return None
        except NetworkError:
            logger.error(f'Network error while getting lyrics for track {track_id}')
            raise
        except Exception:
            logger.exception(f'Failed to get lyrics for track {track_id}')
            return None


def get_lyrics_service() -> LyricsService:
    """Создает и возвращает экземпляр LyricsService."""
    return LyricsService(token=YAM_TOKEN)
