from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

TRACK_TITLE_MAX_LEN = 50


def _trim(text: str, max_len: int = TRACK_TITLE_MAX_LEN) -> str:
    return text if len(text) <= max_len else text[:max_len - 1] + '…'


def get_favorites_kb(data: dict) -> InlineKeyboardMarkup:
    """Клавиатура избранного с пагинацией.

    Args:
        data: словарь с ключами 'results', 'previous', 'next'.
    """
    keyboard = []
    for item in data.get('results', []):
        track_id = str(item['track_id'])
        artist_id = str(item.get('artist_id') or '0')
        title = _trim(item.get('title') or 'Без названия')
        keyboard.append([
            InlineKeyboardButton(
                text=title,
                callback_data=f'download:{track_id}:{artist_id}',
            )
        ])

    nav_buttons: list[InlineKeyboardButton] = []
    if prev_pages := data.get('previous'):
        prev_page = prev_pages[0] if isinstance(prev_pages, list) else prev_pages
        nav_buttons.append(
            InlineKeyboardButton(text='◀️', callback_data=f'favorites:{prev_page}')
        )
    if next_pages := data.get('next'):
        next_page = next_pages[0] if isinstance(next_pages, list) else next_pages
        nav_buttons.append(
            InlineKeyboardButton(text='▶️', callback_data=f'favorites:{next_page}')
        )

    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton(text='❌ Закрыть', callback_data='favorites:close')])
    keyboard.append([InlineKeyboardButton(text='◀️ Назад', callback_data='main:menu')])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
