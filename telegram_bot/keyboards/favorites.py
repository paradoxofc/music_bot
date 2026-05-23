from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_favorites_kb(data: dict, chat_id: int) -> InlineKeyboardMarkup:
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
                callback_data=f"favorites:{chat_id}:{data['previous'][-1]}"
            )
        )
    if data.get('next'):
        nav_buttons.append(
            InlineKeyboardButton(
                text='▶️',
                callback_data=f"favorites:{chat_id}:{data['next'][-1]}"
            )
        )
    keyboard.append(nav_buttons)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
