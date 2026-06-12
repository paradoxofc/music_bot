import logging

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

back_to_admin_button = InlineKeyboardButton(text='Назад', callback_data='admin')


def get_stats_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[back_to_admin_button]])


def get_admin_main_kb() -> InlineKeyboardMarkup:
    stats_button = InlineKeyboardButton(text='📊 Статистика', callback_data='stats')
    report_button = InlineKeyboardButton(text='📋 Отчёт', callback_data='admin:report')
    broadcast_button = InlineKeyboardButton(text='📢 Рассылки', callback_data='broadcast:list:1')
    op_button = InlineKeyboardButton(text='📌 ОП', callback_data='op:list:1')
    get_file_info_button = InlineKeyboardButton(
        text='ℹ️ Получить информацию о файле', callback_data='get_file_info'
    )

    kb = [[stats_button], [report_button], [broadcast_button], [op_button], [get_file_info_button]]
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

    add_broadcast = InlineKeyboardButton(text='Создать', callback_data='broadcast:add')
    back = InlineKeyboardButton(text='В меню', callback_data='admin')
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


def get_op_list_kb(op_setups: dict | None = None) -> InlineKeyboardMarkup:
    kb = []
    if op_setups:
        for item in op_setups.get('results', []):
            prefix = '🟢 ' if item.get('is_active') else ''
            kb.append(
                [
                    InlineKeyboardButton(
                        text=f"{prefix}{item.get('name')}",
                        callback_data=f"op:retrieve:{item.get('id')}",
                    )
                ]
            )
        nav_buttons = []
        if prev_page := op_setups.get('previous_page'):
            nav_buttons.append(InlineKeyboardButton(text='◀️', callback_data=f'op:list:{prev_page}'))
        if next_page := op_setups.get('next_page'):
            nav_buttons.append(InlineKeyboardButton(text='▶️', callback_data=f'op:list:{next_page}'))
        if nav_buttons:
            kb.append(nav_buttons)

    add_button = InlineKeyboardButton(text='➕ Создать', callback_data='op:add')
    back = InlineKeyboardButton(text='🔙 В меню', callback_data='admin')
    kb.append([back, add_button])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_op_retrieve_kb(op_setup_id: str, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = '⏸ Выключить' if is_active else '▶️ Включить'
    toggle_data = f'op:toggle:off:{op_setup_id}' if is_active else f'op:toggle:on:{op_setup_id}'

    kb = [
        [InlineKeyboardButton(text='📝 Изменить название', callback_data=f'op:edit_name:{op_setup_id}')],
        [InlineKeyboardButton(text='💬 Изменить текст', callback_data=f'op:edit_text:{op_setup_id}')],
        [InlineKeyboardButton(text='📢 Изменить каналы', callback_data=f'op:edit_channels:{op_setup_id}')],
        [
            InlineKeyboardButton(text='👤 Превью', callback_data=f'op:preview:{op_setup_id}'),
            InlineKeyboardButton(text=toggle_text, callback_data=toggle_data),
        ],
        [InlineKeyboardButton(text='Назад', callback_data='op:list:1')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)
