import asyncio
import json

import aiohttp
from aiogram.types import BufferedInputFile
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_fixed
from yandex_music import ChartInfo, ClientAsync, DownloadInfo, Track
from yandex_music.exceptions import NetworkError

from ..config import YAM_TOKEN, redis

_yam_service: 'YAMService | None' = None


def _best_download_info(download_info: list[DownloadInfo]) -> DownloadInfo:
    return sorted(download_info, key=lambda info: info.bitrate_in_kbps)[-1]


class YAMService:
    """Сервис для взаимодействия с Яндекс Музыкой."""

    def __init__(self, token: str):
        self.token = token
        self.client = ClientAsync(token=token)

    async def init(self) -> None:
        """Инициализирует клиент и загружает данные аккаунта."""
        await self.client.init()
        logger.info('Yandex Music клиент инициализирован')

    @staticmethod
    def _parse_track_list(tracks: list[Track]) -> list[dict]:
        parsed_results: list[dict] = []
        for track in tracks:
            if not track.available or not track.artists:
                continue
            artist = track.artists[0]
            parsed_results.append(
                {
                    'id': track.id,
                    'title': f'{artist.name} - {track.title}',
                    'artist_id': artist.id,
                }
            )
        return parsed_results

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def search(self, query: str, page: str | int = 0) -> dict | None:
        """Поиск треков по названию."""
        page_num = int(page) if str(page).isdigit() else 0
        search_result = await self.client.search(
            text=query[:200],
            type_='track',
            page=page_num,
        )
        if not search_result or not search_result.tracks or not search_result.tracks.results:
            return None

        return {
            'tracks': self._parse_track_list(search_result.tracks.results),
            'page': page_num,
            'query': query,
        }

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def download_track(self, track_id: str) -> tuple[str, str, BufferedInputFile, BufferedInputFile | None]:
        try:
            track_list = await self.client.tracks(track_id)
            if not track_list:
                raise ValueError('Трек не найден')
            track = track_list[0]

            download_info = await track.get_download_info_async()
            if not download_info:
                raise ValueError('Нет доступных форматов для скачивания')
            best_quality = _best_download_info(download_info)
            url = await best_quality.get_direct_link_async()
            if not url:
                raise Exception('Direct link is None')

            cover_file: BufferedInputFile | None = None

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        raise Exception(f'Failed to download file, status code: {resp.status}')
                    artist = track.artists[0].name if track.artists else 'Неизвестен'
                    title = track.title
                    audio_bytes = await resp.read()

                try:
                    if getattr(track, 'cover_uri', None) and hasattr(track, 'get_cover_url'):
                        cover_url = track.get_cover_url('700x700')
                        async with session.get(cover_url) as c_resp:
                            if c_resp.status == 200:
                                cover_file = BufferedInputFile(await c_resp.read(), filename='cover.jpg')
                except Exception:
                    logger.debug('Не удалось получить обложку трека', exc_info=True)
            return (
                artist,
                title,
                BufferedInputFile(audio_bytes, filename=f'{artist} - {title}.mp3'),
                cover_file,
            )
        except NetworkError:
            raise Exception('Network error while downloading track.')
        except Exception as e:
            raise Exception(f'Download failed: {e}')

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def get_track_info(self, track_id: str) -> tuple[str, int]:
        try:
            track_list = await self.client.tracks(track_id)
            if not track_list:
                raise ValueError('Трек не найден')

            track = track_list[0]
            artist = track.artists[0]
            return f'{artist.name} - {track.title}', artist.id
        except NetworkError:
            raise Exception('Network error while getting track info.')
        except Exception as e:
            raise Exception(f'Failed to get track info: {e}')

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def get_track_direct_link(self, track_id: str) -> tuple[str, str, str, str | None]:
        """Получает прямую ссылку на трек и метаданные для inline-режима."""
        try:
            track_list = await self.client.tracks(track_id)
            if not track_list:
                raise ValueError('Трек не найден')

            track = track_list[0]
            artist = track.artists[0].name if track.artists else 'Неизвестен'
            title = track.title

            download_info = await track.get_download_info_async()
            if not download_info:
                raise ValueError('Нет доступных форматов для скачивания')
            best_quality = _best_download_info(download_info)
            audio_url = await best_quality.get_direct_link_async()

            if not audio_url:
                raise Exception('Direct link is None')

            cover_url = None
            try:
                if getattr(track, 'cover_uri', None) and hasattr(track, 'get_cover_url'):
                    cover_url = track.get_cover_url('700x700')
            except Exception:
                logger.debug('Не удалось получить URL обложки трека', exc_info=True)

            return artist, title, audio_url, cover_url
        except NetworkError:
            raise Exception('Network error while getting track direct link.')
        except Exception as e:
            raise Exception(f'Failed to get track direct link: {e}')

    async def get_track_direct_links_parallel(
        self,
        track_ids: list[str],
        *,
        concurrency: int = 5,
    ) -> dict[str, tuple[str, str, str, str | None]]:
        """Параллельно получает прямые ссылки для списка треков."""
        if not track_ids:
            return {}

        semaphore = asyncio.Semaphore(concurrency)
        results: dict[str, tuple[str, str, str, str | None]] = {}

        async def fetch(track_id: str) -> None:
            async with semaphore:
                try:
                    results[track_id] = await self.get_track_direct_link(track_id)
                except Exception as e:
                    logger.warning(f'Не удалось получить ссылку для inline-трека {track_id}: {e}')

        await asyncio.gather(*(fetch(track_id) for track_id in track_ids))
        return results

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def get_top_chart(self, page: int = 0) -> dict:
        """Возвращает страницу топ-чарта с кэшированием в Redis."""
        cache_key_all = 'yam:top_chart:all'
        ttl_seconds = 3600

        all_tracks_parsed: list[dict] | None = None

        if redis is not None:
            try:
                cached = await redis.get(cache_key_all)
                if cached:
                    all_tracks_parsed = json.loads(cached)
            except Exception:
                logger.debug('Ошибка при получении топ-чарта из кэша')
                all_tracks_parsed = None

        if all_tracks_parsed is None:
            chart: ChartInfo = await self.client.chart()
            tracks = chart.chart.tracks
            all_tracks_parsed = []
            for track in tracks:
                all_tracks_parsed.append(
                    {
                        'id': track.track_id,
                        'title': f'{track.track.artists[0].name} - {track.track.title}',
                        'artist_id': track.track.artists[0].id,
                    }
                )
            if redis is not None:
                try:
                    await redis.set(
                        cache_key_all,
                        json.dumps(all_tracks_parsed, ensure_ascii=False),
                        ex=ttl_seconds,
                    )
                except Exception:
                    logger.debug('Ошибка при сохранении топ-чарта в кэш')

        page_size = 10
        offset = int(page) * page_size
        limit = offset + page_size
        parsed_tracks = all_tracks_parsed[offset:limit]
        return {'page': page, 'tracks': parsed_tracks}

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def search_by_artist(self, artist_id: str, page: int = 0) -> dict:
        artist_tracks = await self.client.artists_tracks(
            artist_id=artist_id,
            page=page,
            page_size=10,
        )
        tracks = artist_tracks.tracks if artist_tracks else []
        parsed_tracks = self._parse_track_list(tracks)
        return {'page': page, 'tracks': parsed_tracks, 'artist_id': artist_id}


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
