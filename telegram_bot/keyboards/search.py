from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ..constants import MIN_ALBUM_TRACKS

TRACK_TITLE_MAX_LEN = 50


def _trim(text: str, max_len: int = TRACK_TITLE_MAX_LEN) -> str:
    return text if len(text) <= max_len else text[:max_len - 1] + '…'


def get_search_kb(
    results: dict,
    *,
    query_token: str | None = None,
    is_artist_search: bool = False,
) -> InlineKeyboardMarkup | None:
    """Клавиатура результатов поиска.

    Args:
        results: словарь с ключами 'tracks', 'page', 'query' (для обычного поиска)
                 или 'tracks', 'page', 'artist_id', 'has_next' (для поиска по артисту).
        query_token: короткий Redis-токен поискового запроса (для кнопок пагинации).
        is_artist_search: True для поиска треков исполнителя.
    """
    tracks = results.get('tracks', [])
    albums = results.get('albums', [])
    if not tracks and not albums:
        return None

    keyboard = []
    page = int(results.get('page', 0))

    # Если найдены альбомы, ставим их на первое место (сверху списка треков)
    if albums and page == 0:
        for album in albums[:2]:
            tr_count = album.get('track_count', 0)
            if tr_count < MIN_ALBUM_TRACKS:
                continue
            album_id = str(album['id'])
            artist = album.get('artist_name', '')
            title = album.get('title', 'Альбом')
            count_str = f' ({tr_count} тр.)' if tr_count else ''
            label = _trim(f'💿 Альбом: {artist} - {title}{count_str}')
            keyboard.append([
                InlineKeyboardButton(
                    text=label,
                    callback_data=f'album:view:{album_id}',
                )
            ])

    for track in tracks:
        track_id = str(track['id'])
        artist_id = str(track.get('artist_id', '0'))
        title = _trim(track.get('title', 'Без названия'))
        keyboard.append([
            InlineKeyboardButton(
                text=title,
                callback_data=f'download:{track_id}:{artist_id}',
            )
        ])


    # Навигационные кнопки
    nav_buttons: list[InlineKeyboardButton] = []
    page = int(results.get('page', 0))

    if is_artist_search:
        artist_id = str(results.get('artist_id', ''))
        has_next = results.get('has_next', False)
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(text='◀️', callback_data=f'artist_search:{artist_id}:{page - 1}')
            )
        if has_next:
            nav_buttons.append(
                InlineKeyboardButton(text='▶️', callback_data=f'artist_search:{artist_id}:{page + 1}')
            )
    elif query_token:
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(text='◀️', callback_data=f'search:{query_token}:{page - 1}')
            )
        # Показываем «вперёд» если пришли треки (если страница неполная — Яндекс вернёт меньше)
        if len(tracks) >= 10:
            nav_buttons.append(
                InlineKeyboardButton(text='▶️', callback_data=f'search:{query_token}:{page + 1}')
            )

    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton(text='◀️ Назад', callback_data='main:menu')])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
