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
from aiogram.types import BotCommand, ErrorEvent
from loguru import logger

from telegram_bot.db import close_db_pool, init_db_pool
from telegram_bot.middlewares import (
    ActivityMiddleware,
    MandatorySubscriptionMiddleware,
    ThrottlingMiddleware,
)
from telegram_bot.config import DEBUG, LOG_LEVEL, TELEGRAM_BOT_TOKEN, admin_user_id, redis
from telegram_bot.router import setup_routers
from telegram_bot.services import (
    close_yam_service,
    init_yam_service,
    start_reminder_scheduler,
    stop_reminder_scheduler,
)


BOT_COMMANDS = [
    BotCommand(command='start', description='Главное меню'),
    BotCommand(command='search', description='Поиск трека'),
    BotCommand(command='favorites', description='Избранное'),
    BotCommand(command='donate', description='Поддержать бота'),
]


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

import socket
from aiohttp import TCPConnector
from aiogram.client.session.aiohttp import AiohttpSession


class IPv4AiohttpSession(AiohttpSession):
    """Принудительно использует IPv4 (AF_INET) для всех запросов к Telegram API."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._connector_init['family'] = socket.AF_INET


bot = Bot(
    TELEGRAM_BOT_TOKEN,
    session=IPv4AiohttpSession(),
    default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
)
dp = Dispatcher()
setup_routers(dp)


from contextlib import suppress
from telegram_bot.utils import get_error_kb


@dp.errors()
async def on_error(event: ErrorEvent) -> None:
    logger.exception(
        'Необработанная ошибка (update_id={}): {}',
        event.update.update_id if event.update else '?',
        event.exception,
    )
    try:
        err = event.exception
        ctx = f"update_id={event.update.update_id if event.update else '?'}"
        kb = get_error_kb(err, context=ctx)
        text = f'❌ Произошла ошибка: {type(err).__name__}'
        if event.update:
            if event.update.message:
                await event.update.message.answer(text=text, reply_markup=kb)
            elif event.update.callback_query and event.update.callback_query.message:
                with suppress(Exception):
                    await event.update.callback_query.answer()
                await event.update.callback_query.message.answer(text=text, reply_markup=kb)
    except Exception as notify_err:
        logger.debug(f'Не удалось отправить сообщение об ошибке: {notify_err}')

    # Возвращаем True, чтобы aiogram считал ошибку обработанной и не
    # обрывал polling на единичном сбое в хендлере.
    return True


activity = ActivityMiddleware(redis)
throttling = ThrottlingMiddleware(redis)
op_subscription = MandatorySubscriptionMiddleware()

dp.message.middleware(activity)
dp.callback_query.middleware(activity)
dp.inline_query.middleware(activity)

dp.message.middleware(throttling)
dp.callback_query.middleware(throttling)
dp.inline_query.middleware(throttling)

dp.message.middleware(op_subscription)
dp.callback_query.middleware(op_subscription)
dp.inline_query.middleware(op_subscription)



async def on_startup() -> None:
    await init_db_pool()
    await init_yam_service()
    start_reminder_scheduler(bot)
    try:
        await bot.set_my_commands(BOT_COMMANDS)
    except Exception as e:
        logger.warning(f'Не удалось установить меню команд: {e}')


async def on_shutdown() -> None:
    """Корректно освобождаем ресурсы — раньше при остановке оставались
    открытые соединения с Postgres, Redis и aiohttp-сессии."""
    logger.info('Остановка бота…')
    stop_reminder_scheduler()
    await close_yam_service()
    await close_db_pool()
    try:
        await redis.aclose()
    except Exception as e:
        logger.warning(f'Ошибка при закрытии Redis: {e}')
    await bot.session.close()
    logger.info('Бот остановлен')



async def main() -> None:
    """Запуск бота."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error('TELEGRAM_BOT_TOKEN не задан. Проверьте .env')
        sys.exit(1)
    if admin_user_id() is None:
        logger.warning('ADMIN_CHAT_ID не задан — админ-панель будет недоступна')
    if DEBUG:
        logger.debug('ADMIN_CHAT_ID={}', admin_user_id())

    await on_startup()
    logger.info('🚀 Бот успешно подключен к Telegram и ожидает сообщений!')
    try:
        await dp.start_polling(
            bot,
            # Не обрабатываем апдейты, накопившиеся за время простоя.
            drop_pending_updates=True,
            allowed_updates=dp.resolve_used_update_types(),
        )
    finally:
        await on_shutdown()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info('Выход по сигналу остановки')
