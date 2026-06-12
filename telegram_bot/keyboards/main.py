from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)


def get_main_kb() -> InlineKeyboardMarkup:
    """Клавиатура главного меню."""
    keyboard = [
        [InlineKeyboardButton(text='🔍 Поиск', callback_data='main:search')],
        [InlineKeyboardButton(text='🔥 Топ-чарт', callback_data='main:chart')],
        [InlineKeyboardButton(text='⭐ Избранное', callback_data='main:favorites')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_top_chart_kb(chart: dict) -> InlineKeyboardMarkup:
    """Клавиатура для топ-чарта."""
    keyboard = []
    for track in chart['tracks']:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=track['title'],
                    callback_data=f"download:{track['id']}:{track['artist_id']}"
                )
            ]
        )
    nav_buttons = []
    if int(chart['page']) > 0:
        nav_buttons.append(
            InlineKeyboardButton(
                text='◀️',
                callback_data=f"chart:{int(chart['page']) - 1}"
            )
        )
    if int(chart['page']) < 9:
        nav_buttons.append(
            InlineKeyboardButton(
                text='▶️',
                callback_data=f"chart:{int(chart['page']) + 1}"
            )
        )
    keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton(text='◀️ Назад', callback_data='main:menu')])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
