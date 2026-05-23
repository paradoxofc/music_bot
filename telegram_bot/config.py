from dotenv import load_dotenv
import os
load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))

from redis.asyncio import Redis

# TELEGRAM_BOT_TOKEN — токен, который выдается в BotFather у Telegram
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

BACKEND_API_URL = os.getenv('BACKEND_API_URL', '')
BACKEND_API_TOKEN = os.getenv('BACKEND_API_TOKEN', '')

# YAM_TOKEN — токен для доступа к Яндекс Музыке (используется для поиска треков)
YAM_TOKEN = os.getenv('YAM_TOKEN', '')

BOT_LINK = os.getenv('BOT_LINK')
TEST_CHAT_ID = os.getenv('TEST_CHAT_ID')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID') or '0'

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
