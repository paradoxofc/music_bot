from dotenv import load_dotenv
import os

load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


# DEBUG=True — подробные логи (ОП, aiogram, backtrace)
DEBUG = _env_bool('DEBUG', False)
LOG_LEVEL = os.getenv('LOG_LEVEL', 'DEBUG' if DEBUG else 'INFO').upper()

from redis.asyncio import Redis

# TELEGRAM_BOT_TOKEN — токен, который выдается в BotFather у Telegram
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

# YAM_TOKEN — токен для доступа к Яндекс Музыке (используется для поиска треков)
YAM_TOKEN = os.getenv('YAM_TOKEN', '')

BOT_LINK = os.getenv('BOT_LINK')
# Канал, куда ведёт кнопка «Добавить текст», если lyrics не найден
LYRICS_REQUEST_URL = os.getenv('LYRICS_REQUEST_URL', 'https://t.me/dev_myz')
TEST_CHAT_ID = os.getenv('TEST_CHAT_ID')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID') or '0'


def admin_user_id() -> int | None:
    """ID администратора или None, если не задан корректно."""
    try:
        user_id = int(ADMIN_CHAT_ID)
    except (TypeError, ValueError):
        return None
    return user_id if user_id > 0 else None

# Redis для продакшена
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_DB = int(os.getenv('REDIS_DB', '1'))
REDIS_URL = os.getenv('REDIS_URL', f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}')

# Создаем подключение к Redis
from redis.asyncio import Redis
redis = Redis.from_url(REDIS_URL, decode_responses=True)

START_GIF_URL = os.getenv('START_GIF_URL', '')

GRAMADS_ON = os.getenv('GRAMADS_ON') == 'True'
GRAMADS_KEY = os.getenv('GRAMADS_KEY', '')

YANDEX_CLIENT_ID = os.getenv('YANDEX_CLIENT_ID', '')
YANDEX_CLIENT_SECRET = os.getenv('YANDEX_CLIENT_SECRET', '')
# Redirect URI для Яндекс OAuth (должен совпадать с указанным в настройках приложения)
# По умолчанию используется https://oauth.yandex.com/verification_code для OOB режима
YANDEX_REDIRECT_URI = os.getenv('YANDEX_REDIRECT_URI', 'https://oauth.yandex.com/verification_code')

