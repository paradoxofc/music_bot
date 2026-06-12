import html
import os

DEFAULT_BOT_LINK = 'https://t.me/search_muzyka_bot?start=ref'


def get_bot_link() -> str:
    """Актуальная ссылка на бота (читается из env при каждом вызове)."""
    link = (os.getenv('BOT_LINK') or DEFAULT_BOT_LINK).strip()
    # Защита от опечатки вида BOT_LINK=https://... в .env
    if link.startswith('BOT_LINK='):
        link = link.removeprefix('BOT_LINK=').strip()
    return link


def get_music_caption() -> str:
    """Подпись к аудио с кликабельной ссылкой (HTML)."""
    safe_link = html.escape(get_bot_link(), quote=True)
    return f'🎧 <a href="{safe_link}">Любимая музыка — в одном боте</a>'


MAIN_TEXT = """
👋 <b>Добро пожаловать!</b>

Отправь в чат <b>название трека</b> или <b>исполнителя</b>.

⭐️ Понравившиеся песни добавляй в избранное.
"""

NONE_FAVORITES_TEXT = """
У вас нет избранных треков.
Нажмите ⭐️ на кнопке под песней, чтобы добавить её сюда.
"""

FAVORITES_TEXT = """
⭐️ <b>Ваше Избранное</b>
"""

TOP_CHAT_TEXT = """
🔥 <b>Чарт недели</b>
"""

# Обратная совместимость; для новых вызовов используйте get_music_caption().
MUSIC_CAPTION_TEXT = get_music_caption()
