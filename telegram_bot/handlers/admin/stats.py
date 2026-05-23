from aiogram import types

from .main import router
from ...db import get_users_stats, get_event_type_stats
from ...constants import EventType
from ...keyboards import get_stats_kb
from ...texts import STATS_MAIN_TEXT, STATS_EVENT_TYPE_TEXT


@router.callback_query(lambda c: c.data == 'stats')
async def main(event: types.Message | types.CallbackQuery) -> None:
    if isinstance(event, types.CallbackQuery):
        method = event.message.edit_text
        await event.answer()
    else:
        method = event.answer

    user_stats = await get_users_stats()
    await method(
        text=STATS_MAIN_TEXT.format(
            total_users=user_stats.get('total', 'None'),
            active_users=user_stats.get('active', 'None'),
        ),
        reply_markup=get_stats_kb()
    )


@router.callback_query(lambda c: c.data.startswith('get_stats'))
async def get_stats(cb: types.CallbackQuery) -> None:
    event_type = int(cb.data.split(':')[-1])
    event_name = EventType.NAMES.get(event_type)
    event_stats = await get_event_type_stats(event_type)

    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text='< Назад', callback_data='stats')]
        ]
    )
    # Форматируем статистику с разностью
    def format_stat(stat_data):
        if isinstance(stat_data, dict) and 'count' in stat_data:
            count = stat_data.get('count', 0)
            diff_formatted = stat_data.get('diff_formatted', '')
            if diff_formatted and diff_formatted != '+0':
                return f"{count} ({diff_formatted})"
            return str(count)
        return str(stat_data)

    await cb.message.edit_text(
        text=STATS_EVENT_TYPE_TEXT.format(
            event_name=event_name,
            today=format_stat(event_stats.get('today')),
            yesterday=format_stat(event_stats.get('yesterday')),
            last_7_days=format_stat(event_stats.get('last_7_days')),
            last_30_days=format_stat(event_stats.get('last_30_days')),
        ),
        reply_markup=kb
    )
    await cb.answer()
