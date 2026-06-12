import asyncio
import logging
import sys
from pathlib import Path

# Добавляем родительскую директорию в sys.path для поддержки абсолютных импортов
# Это необходимо при прямом запуске файла (python __main__.py)
_file = Path(__file__).resolve()
_parent_dir = _file.parent.parent
if str(_parent_dir) not in sys.path:
    sys.path.insert(0, str(_parent_dir))

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent
from loguru import logger

from telegram_bot.db import init_db_pool
from telegram_bot.middlewares import ThrottlingMiddleware, MandatorySubscriptionMiddleware
from telegram_bot.config import DEBUG, LOG_LEVEL, TELEGRAM_BOT_TOKEN, admin_user_id, redis
from telegram_bot.router import setup_routers
from telegram_bot.services import init_yam_service

def setup_logging() -> None:
    logger.remove()
    logger.add(
        sys.stdout,
        level=LOG_LEVEL,
        format='{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}',
        backtrace=DEBUG,
        diagnose=DEBUG,
        colorize=True,
    )
    if DEBUG:
        logging.basicConfig(level=logging.DEBUG)
        for name in ('aiogram', 'aiogram.event', 'aiogram.dispatcher'):
            logging.getLogger(name).setLevel(logging.DEBUG)
        # Сырые ответы Yandex Music в DEBUG засоряют логи и выглядят как ошибки
        logging.getLogger('yandex_music').setLevel(logging.WARNING)
        logger.info('DEBUG режим включён (LOG_LEVEL={}, DEBUG=True)', LOG_LEVEL)


setup_logging()

bot = Bot(
    TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
)
dp = Dispatcher()
setup_routers(dp)


@dp.errors()
async def on_error(event: ErrorEvent) -> None:
    logger.exception(
        'Необработанная ошибка (update_id={}): {}',
        event.update.update_id if event.update else '?',
        event.exception,
    )

throttling = ThrottlingMiddleware(redis)
op_subscription = MandatorySubscriptionMiddleware()

dp.message.middleware(throttling)
dp.callback_query.middleware(throttling)
dp.inline_query.middleware(throttling)

dp.message.middleware(op_subscription)
dp.callback_query.middleware(op_subscription)
dp.inline_query.middleware(op_subscription)


async def main() -> None:
    """Запуск бота."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error('TELEGRAM_BOT_TOKEN не задан. Проверьте .env')
        sys.exit(1)
    if admin_user_id() is None:
        logger.warning('ADMIN_CHAT_ID не задан — админ-панель будет недоступна')
    if DEBUG:
        logger.debug('ADMIN_CHAT_ID={}', admin_user_id())

    await init_db_pool()
    await init_yam_service()

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
