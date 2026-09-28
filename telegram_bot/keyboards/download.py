from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_download_kb(
    track_id: str,
    artist_id: str,
    is_favorite: bool = False,
) -> InlineKeyboardMarkup:
    """Клавиатура под скачанным треком: текст, ещё треки артиста, избранное."""
    keyboard = [
        [InlineKeyboardButton(text='📜 Текст', callback_data=f'get_lyrics:{track_id}')],
        [
            InlineKeyboardButton(
                text='🎤 Ещё треки',
                callback_data=f'artist_search:{artist_id}:0',
            )
        ],
    ]

    if is_favorite:
        keyboard.append([
            InlineKeyboardButton(
                text='💔 Убрать из избранного',
                callback_data=f'delete_from_favorites:{track_id}:{artist_id}',
            )
        ])
    else:
        keyboard.append([
            InlineKeyboardButton(
                text='⭐ В избранное',
                callback_data=f'add_to_favorites:{track_id}',
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_lyrics_not_found_kb(lyrics_request_url: str) -> InlineKeyboardMarkup:
    """Клавиатура «текст не найден» с кнопкой запроса."""
    keyboard = [
        [
            InlineKeyboardButton(
                text='📝 Добавить текст',
                url=lyrics_request_url,
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
