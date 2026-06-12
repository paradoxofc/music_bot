from .config import GRAMADS_ON
from .constants import EventType
from .db import send_event


async def show_advert(chat_id: int):
    """Показывает рекламу пользователю (Gramads)."""
    if not GRAMADS_ON:
        return
    await send_event(event_type=EventType.SHOW_AD, chat_id=chat_id)
