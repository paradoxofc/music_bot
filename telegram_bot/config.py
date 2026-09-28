import os

from dotenv import load_dotenv
from redis.asyncio import Redis

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'))


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        return default


# DEBUG=True — подробные логи (ОП, aiogram, backtrace)
DEBUG = _env_bool('DEBUG', False)
LOG_LEVEL = os.getenv('LOG_LEVEL', 'DEBUG' if DEBUG else 'INFO').upper()

# TELEGRAM_BOT_TOKEN — токен, который выдается в BotFather у Telegram
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

# YAM_TOKEN — токен для доступа к Яндекс Музыке (используется для поиска треков)
YAM_TOKEN = os.getenv('YAM_TOKEN', '')

BOT_LINK = os.getenv('BOT_LINK')
# Канал, куда ведёт кнопка «Добавить текст», если lyrics не найден
LYRICS_REQUEST_URL = os.getenv('LYRICS_REQUEST_URL', 'https://t.me/dev_myz')
TEST_CHAT_ID = os.getenv('TEST_CHAT_ID')

# ADMIN_CHAT_ID поддерживает как один id, так и список через запятую:
# ADMIN_CHAT_ID=12345,67890
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID') or '0'


def _parse_admin_ids(raw: str) -> tuple[int, ...]:
    ids: list[int] = []
    for chunk in raw.replace(';', ',').split(','):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            user_id = int(chunk)
        except (TypeError, ValueError):
            continue
        if user_id > 0:
            ids.append(user_id)
    return tuple(dict.fromkeys(ids))


ADMIN_CHAT_IDS = _parse_admin_ids(ADMIN_CHAT_ID)


def admin_user_id() -> int | None:
    """ID основного администратора или None, если не задан корректно."""
    return ADMIN_CHAT_IDS[0] if ADMIN_CHAT_IDS else None


def is_admin(user_id: int | None) -> bool:
    """True, если пользователь входит в список администраторов."""
    return bool(user_id) and user_id in ADMIN_CHAT_IDS


# Redis для продакшена
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = _env_int('REDIS_PORT', 6379)
REDIS_DB = _env_int('REDIS_DB', 1)
REDIS_URL = os.getenv('REDIS_URL', f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}')

# Создаем подключение к Redis
redis = Redis.from_url(REDIS_URL, decode_responses=True)

START_GIF_URL = os.getenv('START_GIF_URL', '')

GRAMADS_ON = _env_bool('GRAMADS_ON', False)
GRAMADS_KEY = os.getenv('GRAMADS_KEY', '')

YANDEX_CLIENT_ID = os.getenv('YANDEX_CLIENT_ID', '')
YANDEX_CLIENT_SECRET = os.getenv('YANDEX_CLIENT_SECRET', '')
# Redirect URI для Яндекс OAuth (должен совпадать с указанным в настройках приложения)
# По умолчанию используется https://oauth.yandex.com/verification_code для OOB режима
YANDEX_REDIRECT_URI = os.getenv('YANDEX_REDIRECT_URI', 'https://oauth.yandex.com/verification_code')

# --- Троттлинг ---
THROTTLE_MESSAGE_LIMIT = _env_int('THROTTLE_MESSAGE_LIMIT', 1)
THROTTLE_PERIOD = _env_int('THROTTLE_PERIOD', 1)
THROTTLE_INLINE_LIMIT = _env_int('THROTTLE_INLINE_LIMIT', 3)

# --- Обязательная подписка (ОП) ---
# Сколько секунд кэшировать активную ОП и результат проверки подписки.
OP_SETUP_CACHE_TTL = _env_int('OP_SETUP_CACHE_TTL', 30)
OP_USER_CACHE_TTL = _env_int('OP_USER_CACHE_TTL', 600)
# Если бот не может проверить канал (не админ, канал удалён) — пропускать
# пользователя вместо полной блокировки бота.
OP_FAIL_OPEN = _env_bool('OP_FAIL_OPEN', True)

# --- Рассылки ---
BROADCAST_RATE = _env_int('BROADCAST_RATE', 20)  # сообщений в секунду
