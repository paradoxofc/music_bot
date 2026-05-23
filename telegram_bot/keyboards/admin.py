import logging

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ..constants import EventType

back_to_admin_button = InlineKeyboardButton(text='< Назад', callback_data='admin')


def get_stats_kb() -> InlineKeyboardMarkup:
    kb = []
    for value, event in EventType.CHOICES:
        kb.append([InlineKeyboardButton(text=event, callback_data=f'get_stats:{value}')])

    kb.append([back_to_admin_button])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_admin_main_kb() -> InlineKeyboardMarkup:
    stats_button = InlineKeyboardButton(text='📊 Статистика', callback_data='stats')
    broadcast_button = InlineKeyboardButton(text='📢 Рассылки', callback_data='broadcast:list:1')
    get_file_info_button = InlineKeyboardButton(
        text='ℹ️ Получить информацию о файле', callback_data='get_file_info'
    )

    kb = [[stats_button], [broadcast_button], [get_file_info_button]]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_broadcasts_kb(broadcasts: dict | None = None) -> InlineKeyboardMarkup:
    kb = []
    if broadcasts:
        for broadcast in broadcasts.get('results', []):
            kb.append(
                [
                    InlineKeyboardButton(
                        text=broadcast.get('name'),
                        callback_data=f"broadcast:retrieve:{broadcast.get('id')}"
                    )
                ]
            )
        nav_buttons = []
        if prev_page := broadcasts.get('previous_page'):
            nav_buttons.append(
                InlineKeyboardButton(text='◀️', callback_data=f'broadcast:list:{prev_page}')
            )
        if next_page := broadcasts.get('next_page'):
            nav_buttons.append(
                InlineKeyboardButton(text='▶️', callback_data=f'broadcast:list:{next_page}')
            )
        if nav_buttons:
            kb.append(nav_buttons)

    add_broadcast = InlineKeyboardButton(text='➕ Создать', callback_data='broadcast:add')
    back = InlineKeyboardButton(text='🔙 В меню', callback_data='admin')
    kb.append([back, add_broadcast])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_broadcast_retrieve_kb(broadcast_id: str) -> InlineKeyboardMarkup:
    edit_name_button = InlineKeyboardButton(
        text='📝 Изменить название',
        callback_data=f'broadcast:edit_name:{broadcast_id}'
    )
    edit_text_button = InlineKeyboardButton(
        text='💬 Изменить текст',
        callback_data=f'broadcast:edit_text:{broadcast_id}'
    )
    edit_media_button = InlineKeyboardButton(
        text='📎 Изменить вложение',
        callback_data=f'broadcast:edit_media:{broadcast_id}'
    )
    edit_buttons_button = InlineKeyboardButton(
        text='🔘 Изменить кнопки',
        callback_data=f'broadcast:edit_buttons:{broadcast_id}'
    )
    send_to_self_button = InlineKeyboardButton(
        text='👤 Отправить себе',
        callback_data=f'broadcast:send:self:{broadcast_id}'
    )
    send_to_all_button = InlineKeyboardButton(
        text='🚀 Запустить',
        callback_data=f'broadcast:send:all:{broadcast_id}'
    )
    back_to_broadcast_list_button = InlineKeyboardButton(
        text='< Назад',
        callback_data=f'broadcast:list:1'
    )
    kb = [
        [edit_name_button],
        [edit_text_button],
        [edit_media_button],
        [edit_buttons_button],
        [send_to_self_button, send_to_all_button],
        [back_to_broadcast_list_button]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)
