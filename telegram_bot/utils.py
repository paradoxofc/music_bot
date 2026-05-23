from .config import GRAMADS_ON


async def show_advert(chat_id: int):
    """Показывает рекламу пользователю (Gramads).

    В текущей конфигурации внешний запрос и логирование в backend отключены.
    """
    if not GRAMADS_ON:
        return

    # Можно добавить локальную логику показа рекламы, если понадобится.
    return
