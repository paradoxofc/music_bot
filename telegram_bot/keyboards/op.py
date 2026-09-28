from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_op_subscribe_kb(channels: list[dict]) -> InlineKeyboardMarkup:
    """Клавиатура обязательной подписки: кнопки каналов + «Проверить подписку»."""
    keyboard = []
    for channel in channels:
        button_text = channel.get('button_text', 'Канал')
        invite_url = channel.get('invite_url')
        if invite_url:
            keyboard.append([
                InlineKeyboardButton(text=button_text, url=invite_url)
            ])
        else:
            # Если нет invite_url, показываем channel_ref как текст
            ref = channel.get('channel_ref', '')
            url = f'https://t.me/{ref.lstrip("@")}' if ref.startswith('@') else None
            if url:
                keyboard.append([
                    InlineKeyboardButton(text=button_text, url=url)
                ])

    keyboard.append([
        InlineKeyboardButton(text='✅ Проверить подписку', callback_data='op:check')
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
