import asyncio
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
from loguru import logger

from telegram_bot.middlewares import ThrottlingMiddleware
from telegram_bot.config import TELEGRAM_BOT_TOKEN, redis
from telegram_bot.router import setup_routers

logger.remove()
logger.add(
    sys.stdout,
    level='DEBUG',
    format='{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}',
    backtrace=True,
    colorize=True
)

bot = Bot(
    TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
)
dp = Dispatcher()
setup_routers(dp)

throttling = ThrottlingMiddleware(redis)
dp.message.middleware(throttling)
dp.callback_query.middleware(throttling)
dp.inline_query.middleware(throttling)


async def main() -> None:
    """Запуск бота."""
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
