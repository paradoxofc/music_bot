import random
import json

import aiohttp
from aiogram.types import BufferedInputFile
from tenacity import retry, stop_after_attempt, wait_fixed
from yandex_music import ClientAsync, ChartInfo
from yandex_music.exceptions import NetworkError
from loguru import logger

from ..config import YAM_TOKEN, redis


class YAMService:
    """Сервис для взаимодействия с яндекс музыкой."""

    def __init__(self, token):
        """Инициализация сервиса."""
        self.token = token
        self.client = ClientAsync(token=token)

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def search(self, query: str, page: str = 0) -> dict | None:
        """Поиск треков по названию."""
        url = f'{self.client.base_url}/search/instant/mixed'

        params = {
            'text': query[:200],
            'nocorrect': str(False),
            'type': 'all',
            'filter': 'track',
            'page': page,
            'playlist-in-best': str(True),
            'pageSize': 10,
            'last_page': 'false'
        }

        response = await self.client._request.get(url, params)  # noqa
        result = dict()
        result['last_page'] = response.get('last_page')
        result['tracks'] = self._parse_search_results(response.get('results'))
        result['page'] = page
        result['query'] = query
        return result

    @staticmethod
    def _parse_search_results(data: dict) -> list[dict] | None:
        """Парсит результат поиска треков."""
        if not data:
            return None

        parsed_results = []
        for item in data:
            if isinstance(item, dict) and item.get('type') == 'track':
                track = item.get('track', {})
                if not track.get('available') or not track.get('artists'):
                    continue
                title = track.get('title')
                track_id = track.get('id')
                artist = track['artists'][0]['name']
                artist_id = track['artists'][0]['id']
                parsed_results.append(
                    {
                        'id': track_id,
                        'title': f'{artist} - {title}',
                        'artist_id': artist_id,
                    }
                )
        return parsed_results

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def download_track(self, track_id: str) -> tuple[str, str, BufferedInputFile, BufferedInputFile | None]:
        try:
            track = await self.client.tracks(track_id)
            track = track[0]

            download_info = await track.get_download_info_async()
            best_quality = sorted(download_info, key=lambda x: x['bitrate_in_kbps'])[-1]
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
                raise ValueError("Трек не найден")

            track = track_list[0]
            artist = track.artists[0]
            return f'{artist.name} - {track.title}', artist.id
        except NetworkError:
            raise Exception("Network error while getting track info.")
        except Exception as e:
            raise Exception(f"Failed to get track info: {e}")

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def get_track_direct_link(self, track_id: str) -> tuple[str, str, str, str | None]:
        """Получает прямую ссылку на трек и метаданные для inline-режима.
        
        Returns:
            tuple: (artist_name, title, audio_url, cover_url)
        """
        try:
            track_list = await self.client.tracks(track_id)
            if not track_list:
                raise ValueError("Трек не найден")
            
            track = track_list[0]
            artist = track.artists[0].name if track.artists else 'Неизвестен'
            title = track.title
            
            download_info = await track.get_download_info_async()
            best_quality = sorted(download_info, key=lambda x: x['bitrate_in_kbps'])[-1]
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
            raise Exception("Network error while getting track direct link.")
        except Exception as e:
            raise Exception(f"Failed to get track direct link: {e}")

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def get_top_chart(self, page: int = 0) -> dict:
        """Возвращает страницу топ-чарта с кэшированием в Redis."""
        cache_key_all = 'yam:top_chart:all'
        ttl_seconds = 3600  # 1 час

        all_tracks_parsed: list[dict] | None = None

        # Пытаемся получить из кэша, если Redis доступен
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
            # Сохраняем в кэш, если Redis доступен
            if redis is not None:
                try:
                    await redis.set(cache_key_all, json.dumps(all_tracks_parsed, ensure_ascii=False), ex=ttl_seconds)
                except Exception:
                    logger.debug('Ошибка при сохранении топ-чарта в кэш')

        page_size = 10
        offset = int(page) * page_size
        limit = offset + page_size
        parsed_tracks = all_tracks_parsed[offset:limit]
        return {'page': page, 'tracks': parsed_tracks}

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def search_by_artist(self, artist_id: str, page: int = 0) -> dict:
        tracks = await self.client.artists_tracks(artist_id=artist_id, page=page, page_size=10)

        parsed_tracks = []
        for track in tracks:
            if track.available:
                parsed_tracks.append(
                    {
                        'id': track.id,
                        'title': f'{track.artists[0].name} - {track.title}',
                        'artist_id': track.artists[0].id,
                    }
                )

        result = {'page': page, 'tracks': parsed_tracks, 'artist_id': artist_id}
        return result

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def get_playlist_tracks(self, kind: str) -> list:
        """Возвращает 5 случайных треков из плейлиста."""
        playlist_result = await self.client.users_playlists(kind=kind, user_id='music-blog')

        # Извлекаем треки из результата
        all_tracks = playlist_result.tracks
        count_tracks = 5

        # Выбираем случайные 5 треков
        selected_tracks = random.sample(all_tracks, min(count_tracks, len(all_tracks)))
        return selected_tracks


def get_yam_service() -> YAMService:
    return YAMService(token=YAM_TOKEN)
