from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_favorites_kb(data: dict) -> InlineKeyboardMarkup:
    keyboard = []
    for track in data['results']:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=track['title'],
                    callback_data=f"download:{track['track_id']}:{track['artist_id']}"
                )
            ]
        )
    nav_buttons = []
    if data.get('previous'):
        nav_buttons.append(
            InlineKeyboardButton(
                text='◀️',
                callback_data=f"favorites:{data['previous'][-1]}"
            )
        )
    if data.get('next'):
        nav_buttons.append(
            InlineKeyboardButton(
                text='▶️',
                callback_data=f"favorites:{data['next'][-1]}"
            )
        )
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append(
        [InlineKeyboardButton(text='◀️ Назад', callback_data='main:menu')]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
