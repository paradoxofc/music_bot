from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_search_kb(search_result: dict, is_artist_search: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура для результатов поиска треков."""
    keyboard = []
    for track in search_result['tracks']:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=track['title'],
                    callback_data=f"download:{track['id']}:{track['artist_id']}"
                )
            ]
        )
    nav_buttons = []
    page_num = int(str(search_result.get('page', '0') or '0'))
    if page_num > 0:
        if is_artist_search:
            nav_buttons.append(
                InlineKeyboardButton(
                    text='◀️',
                    callback_data=f"artist_search:{search_result['artist_id']}:{page_num - 1}"
                )
            )
        else:
            back_button = InlineKeyboardButton(
                text='◀️',
                callback_data=f"search:{search_result['query']}:{page_num - 1}"
            )
            if len(back_button.callback_data.encode('utf-8')) < 64:
                nav_buttons.append(back_button)
    nav_buttons.append(
        InlineKeyboardButton(
            text='❌',
            callback_data='delete_message'
        )
    )
    if is_artist_search:
        nav_buttons.append(
            InlineKeyboardButton(
                text='▶️',
                callback_data=f"artist_search:{search_result['artist_id']}:{int(search_result['page']) + 1}"
            )
        )
    else:
        next_button = InlineKeyboardButton(
            text='▶️',
            callback_data=f"search:{search_result['query']}:{int(search_result['page']) + 1}"
        )
        if len(next_button.callback_data.encode('utf-8')) < 64:
            nav_buttons.append(next_button)
    keyboard.append(nav_buttons)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
