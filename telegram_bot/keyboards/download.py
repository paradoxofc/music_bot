from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_download_kb(
    track_id: str,
    artist_id: str | int,
    is_favorite: bool = False
) -> InlineKeyboardMarkup:
    kb = []
    if not is_favorite:
        kb.append(
            [InlineKeyboardButton(
                text='⭐ В избранное',
                callback_data=f'add_to_favorites:{track_id}'
            )]
        )
    else:
        kb.append(
            [InlineKeyboardButton(
                text='⭐ Удалить из избранного',
                callback_data=f'delete_from_favorites:{track_id}:{artist_id}'
            )]
        )
    kb.append(
        [InlineKeyboardButton(
            text='📜 Текст',
            callback_data=f'get_lyrics:{track_id}',
        )]
    )
    kb.append(
        [InlineKeyboardButton(
            text='🔎 Все треки исполнителя',
            callback_data=f'artist_search:{artist_id}:0'
        )]
    )
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_lyrics_not_found_kb(channel_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Сообщить об ошибке', url=channel_url)],
        ]
    )
