from aiogram import types

from .main import router
from ...constants import EventType
from ...db import (
    get_users_stats,
    get_registration_stats,
    get_event_type_stats,
    get_sent_broadcasts_count,
)
from ...keyboards import get_stats_kb
from ...texts import STATS_MAIN_TEXT, format_event_stats_block


async def _build_stats_text() -> str:
    user_stats = await get_users_stats()
    blocks: list[str] = []

    for event_type, name in EventType.CHOICES:
        if event_type == EventType.REGISTRATION:
            stats = await get_registration_stats()
            total = user_stats.get('total', 0)
        elif event_type == EventType.BROADCAST:
            stats = await get_event_type_stats(event_type)
            total = await get_sent_broadcasts_count()
        else:
            stats = await get_event_type_stats(event_type)
            total = stats.get('total', 0)
        blocks.append(format_event_stats_block(name, stats, total=total))

    return STATS_MAIN_TEXT.format(
        total_users=user_stats.get('total', 0),
        active_users=user_stats.get('active', 0),
        blocked_users=user_stats.get('blocked', 0),
        metrics='\n\n'.join(blocks),
    )


async def _show_stats_menu(chat_id: int, message: types.Message | None, bot) -> None:
    text = await _build_stats_text()
    markup = get_stats_kb()

    if message and not message.text:
        await message.delete()
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
        return

    if message:
        await message.edit_text(text=text, reply_markup=markup)
        return

    await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)


@router.callback_query(lambda c: c.data == 'stats')
async def stats_menu(cb: types.CallbackQuery) -> None:
    await cb.answer()
    await _show_stats_menu(cb.message.chat.id, cb.message, cb.bot)
