from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_op_subscribe_kb(channels: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for channel in channels:
        url = channel.get('invite_url')
        if not url:
            ref = channel['channel_ref'].lstrip('@')
            url = f'https://t.me/{ref}'
        rows.append([InlineKeyboardButton(text=channel['button_text'], url=url)])
    rows.append([InlineKeyboardButton(text='✅ Проверить подписку', callback_data='op:check')])
    return InlineKeyboardMarkup(inline_keyboard=rows)
