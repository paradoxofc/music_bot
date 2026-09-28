import asyncio
import json

import aiohttp
from aiogram.types import BufferedInputFile
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed
from yandex_music import Album, ChartInfo, ClientAsync, DownloadInfo, Track
from yandex_music.exceptions import NetworkError


from ..config import YAM_TOKEN, redis
from ..constants import MAX_TG_UPLOAD, MIN_ALBUM_TRACKS

_yam_service: 'YAMService | None' = None

# Сетевые ошибки имеет смысл повторять, логические (трек не найден) — нет.
RETRY_EXCEPTIONS = (NetworkError, aiohttp.ClientError, asyncio.TimeoutError)

CHART_PAGE_SIZE = 10
DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(total=120, sock_connect=15)


class TrackNotFoundError(Exception):
    """Трек недоступен или не существует."""


class TrackTooLargeError(Exception):
    """Файл трека больше лимита Telegram."""


def _best_download_info(download_info: list[DownloadInfo]) -> DownloadInfo:
    if not download_info:
        raise TrackNotFoundError('Нет доступных форматов для скачивания')
    # Исключаем превью-фрагменты (~30 сек): Яндекс отдаёт их с флагом preview=True.
    # Без этой фильтрации алгоритм мог выбрать превью с высоким битрейтом вместо
    # полного трека с чуть более низким — пользователь получал обрезанный файл.
    full_tracks = [info for info in download_info if not info.preview]
    candidates = full_tracks if full_tracks else download_info  # fallback, если всё превью
    return sorted(candidates, key=lambda info: info.bitrate_in_kbps or 0)[-1]


class YAMService:
    """Сервис для взаимодействия с Яндекс Музыкой."""

    def __init__(self, token: str):
        self.token = token
        self.client = ClientAsync(token=token)
        self._session: aiohttp.ClientSession | None = None

    async def init(self) -> None:
        """Инициализирует клиент и загружает данные аккаунта."""
        await self.client.init()
        logger.info('Yandex Music клиент инициализирован')

    async def close(self) -> None:
        """Закрывает HTTP-сессию при остановке бота."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    def _get_session(self) -> aiohttp.ClientSession:
        """Одна переиспользуемая сессия вместо новой на каждый трек."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=DOWNLOAD_TIMEOUT)
        return self._session

    @staticmethod
    def _parse_track_list(tracks: list[Track]) -> list[dict]:
        parsed_results: list[dict] = []
        for track in tracks:
            if not track.available or not track.artists:
                continue
            artist = track.artists[0]
            parsed_results.append(
                {
                    # id всегда строка из цифр: он уезжает в callback_data и
                    # проверяется валидатором is_valid_track_id.
                    'id': str(track.id),
                    'title': f'{artist.name} - {track.title}',
                    'artist_id': str(artist.id),
                }
            )
        return parsed_results

    async def _get_track(self, track_id: str) -> Track:
        track_list = await self.client.tracks(track_id)
        if not track_list or not track_list[0]:
            raise TrackNotFoundError(f'Трек {track_id} не найден')
        return track_list[0]

    @staticmethod
    def _album_cover_url(album: Album) -> str | None:
        try:
            cover_uri = getattr(album, 'cover_uri', None)
            if not cover_uri:
                return None
            if hasattr(album, 'get_cover_url'):
                return album.get_cover_url('700x700')
            return f'https://{cover_uri.replace("%%", "700x700")}'
        except Exception:
            return None

    @staticmethod
    def _get_album_artist(album: Album) -> tuple[str, str]:
        """Возвращает (artist_name, artist_id) безопасно для любых объектов Album."""
        artist_name = 'Неизвестен'
        artist_id = ''
        if getattr(album, 'artists', None) and album.artists:
            first_artist = album.artists[0]
            artist_name = getattr(first_artist, 'name', None) or 'Неизвестен'
            artist_id = str(getattr(first_artist, 'id', '') or '')
        elif callable(getattr(album, 'artists_name', None)):
            try:
                names = album.artists_name()
                if names:
                    artist_name = names[0]
            except Exception:
                pass
        return artist_name, artist_id

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type(RETRY_EXCEPTIONS),
        reraise=True,
    )
    async def get_album_with_tracks(self, album_id: str | int) -> dict | None:
        """Получает альбом со всеми треками."""
        try:
            album: Album = await self.client.albums_with_tracks(album_id)
        except Exception as e:
            logger.warning(f'Не удалось получить альбом {album_id}: {e}')
            return None

        if not album:
            return None

        artist_name, artist_id = self._get_album_artist(album)
        title = album.title or 'Без названия'
        year = getattr(album, 'year', None)

        all_tracks: list[Track] = []
        if album.volumes:
            for vol in album.volumes:
                for track in vol:
                    if track and track.available:
                        all_tracks.append(track)

        parsed_tracks = self._parse_track_list(all_tracks)
        return {
            'id': str(album.id),
            'title': title,
            'full_title': f'{artist_name} - {title}',
            'artist_name': artist_name,
            'artist_id': artist_id,
            'year': year,
            'track_count': len(parsed_tracks),
            'tracks': parsed_tracks,
            'cover_url': self._album_cover_url(album),
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type(RETRY_EXCEPTIONS),
        reraise=True,
    )
    async def search(self, query: str, page: str | int = 0) -> dict | None:
        """Поиск треков и альбомов по названию."""
        page_num = int(page) if str(page).isdigit() else 0
        search_result = await self.client.search(
            text=query[:200],
            type_='all',
            page=page_num,
        )
        if not search_result:
            return None

        tracks = []
        if search_result.tracks and search_result.tracks.results:
            tracks = self._parse_track_list(search_result.tracks.results)

        albums = []
        if search_result.albums and search_result.albums.results:
            for alb in search_result.albums.results:
                if not alb:
                    continue
                track_count = getattr(alb, 'track_count', 0) or 0
                if track_count < MIN_ALBUM_TRACKS:
                    continue
                artist, artist_id = self._get_album_artist(alb)
                albums.append({
                    'id': str(alb.id),
                    'title': alb.title or 'Без названия',
                    'full_title': f'{artist} - {alb.title or "Без названия"}',
                    'artist_name': artist,
                    'artist_id': artist_id,
                    'track_count': track_count,
                    'year': getattr(alb, 'year', None),
                    'cover_url': self._album_cover_url(alb),
                })

        # Если в best попал альбом, ставим его в самое начало списка альбомов
        # только если в нём от 4 треков (иначе это сингл)
        if getattr(search_result, 'best', None) and search_result.best.type == 'album':
            best_album = search_result.best.result
            best_track_count = getattr(best_album, 'track_count', 0) or 0
            if (
                best_album
                and best_track_count >= MIN_ALBUM_TRACKS
                and str(best_album.id) not in {a['id'] for a in albums}
            ):
                artist, artist_id = self._get_album_artist(best_album)
                albums.insert(0, {
                    'id': str(best_album.id),
                    'title': best_album.title or 'Без названия',
                    'full_title': f'{artist} - {best_album.title or "Без названия"}',
                    'artist_name': artist,
                    'artist_id': artist_id,
                    'track_count': best_track_count,
                    'year': getattr(best_album, 'year', None),
                    'cover_url': self._album_cover_url(best_album),
                })

        if not tracks and not albums:
            return None

        return {
            'tracks': tracks,
            'albums': albums,
            'page': page_num,
            'query': query,
        }


    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type(RETRY_EXCEPTIONS),
        reraise=True,
    )
    async def download_track(
        self, track_id: str
    ) -> tuple[str, str, BufferedInputFile, BufferedInputFile | None, int]:
        """Скачивает трек и обложку через встроенные методы библиотеки.

        Бросает TrackNotFoundError / TrackTooLargeError / ValueError.
        Возвращает (artist, title, audio, cover, duration_sec).
        """
        track = await self._get_track(track_id)

        artist = track.artists[0].name if track.artists else 'Неизвестен'
        title = track.title or 'Без названия'
        duration_sec = int((track.duration_ms or 0) / 1000)

        audio_bytes = await track.download_bytes_async(bitrate_in_kbps=192)
        if len(audio_bytes) < 100 * 1024:
            raise ValueError(
                f'Файл трека слишком мал ({len(audio_bytes)} байт), возможно, отдано превью'
            )

        if len(audio_bytes) > MAX_TG_UPLOAD:
            raise TrackTooLargeError('Трек больше лимита Telegram')

        cover_file: BufferedInputFile | None = None
        try:
            if getattr(track, 'cover_uri', None):
                cover_bytes = await track.download_cover_bytes_async('700x700')
                if cover_bytes:
                    cover_file = BufferedInputFile(cover_bytes, filename='cover.jpg')
        except Exception as e:
            logger.debug(f'Не удалось получить обложку трека {track_id}: {e}')

        audio_file = BufferedInputFile(audio_bytes, filename=f'{artist} - {title}.mp3')
        return (
            artist,
            title,
            audio_file,
            cover_file,
            duration_sec,
        )

    @staticmethod
    def _cover_url(track: Track) -> str | None:
        try:
            cover_uri = getattr(track, 'cover_uri', None)
            if not cover_uri:
                return None
            # cover_uri имеет вид «avatars.yandex.net/...%%» — заменяем %% на размер.
            # get_cover_url — синхронный helper, но на случай его отсутствия
            # используем прямую замену как надёжный fallback.
            if hasattr(track, 'get_cover_url'):
                return track.get_cover_url('700x700')
            return f'https://{cover_uri.replace("%%", "700x700")}'
        except Exception:
            logger.debug('Не удалось собрать URL обложки трека')
        return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type(RETRY_EXCEPTIONS),
        reraise=True,
    )
    async def get_track_info(self, track_id: str) -> tuple[str, str]:
        track = await self._get_track(track_id)
        if not track.artists:
            return track.title or 'Без названия', ''
        artist = track.artists[0]
        return f'{artist.name} - {track.title}', str(artist.id)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type(RETRY_EXCEPTIONS),
        reraise=True,
    )
    async def get_track_direct_link(self, track_id: str) -> tuple[str, str, str, str | None, int]:
        """Получает прямую ссылку на трек и метаданные для inline-режима."""
        track = await self._get_track(track_id)
        artist = track.artists[0].name if track.artists else 'Неизвестен'
        title = track.title or 'Без названия'
        duration_seconds = int((track.duration_ms or 0) / 1000)

        download_info = await track.get_download_info_async()
        best_quality = _best_download_info(download_info)
        audio_url = await best_quality.get_direct_link_async()
        if not audio_url:
            raise TrackNotFoundError('Яндекс не вернул прямую ссылку на трек')

        return artist, title, audio_url, self._cover_url(track), duration_seconds

    async def get_track_direct_links_parallel(
        self,
        track_ids: list[str],
        *,
        concurrency: int = 5,
    ) -> dict[str, tuple[str, str, str, str | None, int]]:
        """Параллельно получает прямые ссылки для списка треков."""
        if not track_ids:
            return {}

        semaphore = asyncio.Semaphore(concurrency)
        results: dict[str, tuple[str, str, str, str | None, int]] = {}

        async def fetch(track_id: str) -> None:
            async with semaphore:
                try:
                    results[track_id] = await self.get_track_direct_link(track_id)
                except Exception as e:
                    logger.warning(f'Не удалось получить ссылку для inline-трека {track_id}: {e}')

        await asyncio.gather(*(fetch(track_id) for track_id in track_ids))
        return results

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type(RETRY_EXCEPTIONS),
        reraise=True,
    )
    async def get_top_chart(self, page: int = 0) -> dict:
        """Возвращает страницу топ-чарта с кэшированием в Redis."""
        cache_key_all = 'yam:top_chart:all'
        ttl_seconds = 3600

        all_tracks_parsed: list[dict] | None = None

        try:
            cached = await redis.get(cache_key_all)
            if cached:
                all_tracks_parsed = json.loads(cached)
        except Exception:
            logger.debug('Ошибка при получении топ-чарта из кэша')
            all_tracks_parsed = None

        if all_tracks_parsed is None:
            chart: ChartInfo = await self.client.chart()
            all_tracks_parsed = []
            for item in chart.chart.tracks:
                track = item.track
                if not track or not track.artists:
                    continue
                artist = track.artists[0]
                all_tracks_parsed.append(
                    {
                        # Важно: item.track_id у Яндекса может быть составным
                        # («12345:678»), а в callback_data нужен чистый id трека.
                        'id': str(track.id),
                        'title': f'{artist.name} - {track.title}',
                        'artist_id': str(artist.id),
                    }
                )
            try:
                await redis.set(
                    cache_key_all,
                    json.dumps(all_tracks_parsed, ensure_ascii=False),
                    ex=ttl_seconds,
                )
            except Exception:
                logger.debug('Ошибка при сохранении топ-чарта в кэш')

        page = max(0, int(page))
        offset = page * CHART_PAGE_SIZE
        parsed_tracks = all_tracks_parsed[offset:offset + CHART_PAGE_SIZE]
        return {
            'page': page,
            'tracks': parsed_tracks,
            # has_next нужен клавиатуре, чтобы «▶️» не вела на пустую страницу.
            'has_next': offset + CHART_PAGE_SIZE < len(all_tracks_parsed),
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type(RETRY_EXCEPTIONS),
        reraise=True,
    )
    async def search_by_artist(self, artist_id: str, page: int = 0) -> dict:
        artist_tracks = await self.client.artists_tracks(
            artist_id=artist_id,
            page=page,
            page_size=10,
        )
        tracks = artist_tracks.tracks if artist_tracks else []
        parsed_tracks = self._parse_track_list(tracks)

        albums = []
        if int(page) == 0:
            try:
                artist_albums = await self.client.artists_direct_albums(
                    artist_id=artist_id, page=0, page_size=5
                )
                if artist_albums and artist_albums.albums:
                    for alb in artist_albums.albums:
                        if not alb:
                            continue
                        track_count = getattr(alb, 'track_count', 0) or 0
                        if track_count < MIN_ALBUM_TRACKS:
                            continue
                        artist_name, artist_id = self._get_album_artist(alb)
                        albums.append({
                            'id': str(alb.id),
                            'title': alb.title or 'Без названия',
                            'full_title': f'{artist_name} - {alb.title or "Без названия"}',
                            'artist_name': artist_name,
                            'artist_id': artist_id,
                            'track_count': track_count,
                            'year': getattr(alb, 'year', None),
                            'cover_url': self._album_cover_url(alb),
                        })
            except Exception as e:
                logger.debug(f'Не удалось получить альбомы артиста {artist_id}: {e}')

        return {
            'page': page,
            'tracks': parsed_tracks,
            'albums': albums,
            'artist_id': artist_id,
            'has_next': len(parsed_tracks) == 10,
        }



async def init_yam_service() -> YAMService:
    """Создаёт и инициализирует singleton YAMService."""
    global _yam_service
    if _yam_service is None:
        _yam_service = YAMService(token=YAM_TOKEN)
        if YAM_TOKEN:
            await _yam_service.init()
        else:
            logger.warning('YAM_TOKEN пустой — клиент Yandex Music не авторизован')
    return _yam_service


def get_yam_service() -> YAMService:
    """Возвращает инициализированный YAMService."""
    if _yam_service is None:
        raise RuntimeError('YAMService не инициализирован. Вызовите init_yam_service() при старте бота.')
    return _yam_service


async def close_yam_service() -> None:
    """Закрывает HTTP-сессию сервиса при остановке бота."""
    global _yam_service
    if _yam_service is not None:
        await _yam_service.close()
        _yam_service = None
