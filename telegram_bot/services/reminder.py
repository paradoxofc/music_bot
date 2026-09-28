import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from aiogram import Bot, types
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from loguru import logger

from ..config import BROADCAST_RATE, redis
from ..db import (
    get_inactive_user_ids,
    set_blocked_status_bulk,
    set_reminded_status_bulk,
)

MSK_TZ = timezone(timedelta(hours=3))
REMINDER_TEXT = (
    'Музыка нас связала... Но ты не заходишь, уже забыл про бота, '
    'который бесплатно скачивает музыку, исправим?'
)
REMINDER_BUTTON_TEXT = 'Го исправлять!'
TARGET_SEND_DURATION_SECONDS = 3600  # 1 час на распределение нагрузки

_scheduler_task: asyncio.Task | None = None


def get_reminder_kb() -> types.InlineKeyboardMarkup:
    """Инлайн-кнопка для возврата в бота."""
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text=REMINDER_BUTTON_TEXT,
                    callback_data='reminder:fix',
                )
            ]
        ]
    )


def get_seconds_until_next_reminder(target_hour: int = 15, target_minute: int = 15) -> float:
    """Вычисляет количество секунд до следующего наступления 15:15 по МСК."""
    now_msk = datetime.now(MSK_TZ)
    target = now_msk.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if target <= now_msk:
        target += timedelta(days=1)
    return max(1.0, (target - now_msk).total_seconds())


async def send_inactive_reminders(bot: Bot, days: int = 3) -> tuple[int, int]:
    """Отправляет напоминание пользователям, не заходившим в бота 3+ дня, плавно в течение 1 часа."""
    inactive_user_ids = await get_inactive_user_ids(days=days)
    if not inactive_user_ids:
        logger.info('Напоминалка: нет неактивных пользователей (3+ дня)')
        return 0, 0

    total = len(inactive_user_ids)
    # Распределяем отправку равномерно на 1 час (3600 секунд)
    delay = max(0.05, min(5.0, TARGET_SEND_DURATION_SECONDS / total))
    estimated_minutes = round((total * delay) / 60, 1)
    logger.info(
        f'Напоминалка: найдено {total} неактивных пользователей. '
        f'Рассылка распределена на ~{estimated_minutes} мин. (пауза {delay:.2f} сек. между сообщениями)'
    )

    sent = 0
    failed = 0
    blocked: list[int] = []
    reminded: list[int] = []
    markup = get_reminder_kb()

    for chat_id in inactive_user_ids:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=REMINDER_TEXT,
                reply_markup=markup,
            )
            sent += 1
            reminded.append(chat_id)
        except TelegramRetryAfter as e:
            logger.warning(f'Напоминалка flood control: пауза {e.retry_after}s')
            await asyncio.sleep(e.retry_after)
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=REMINDER_TEXT,
                    reply_markup=markup,
                )
                sent += 1
                reminded.append(chat_id)
            except (TelegramForbiddenError, TelegramBadRequest) as retry_err:
                failed += 1
                err_msg = str(retry_err).lower()
                if isinstance(retry_err, TelegramForbiddenError) or any(
                    s in err_msg for s in ('chat not found', 'user not found', 'deactivated', 'bot was blocked', "can't initiate")
                ):
                    blocked.append(chat_id)
            except Exception as e:
                failed += 1
                logger.warning(f'Напоминалка: повтор для {chat_id} не удался: {e}')
        except TelegramForbiddenError:
            # Пользователь заблокировал бота
            failed += 1
            blocked.append(chat_id)
        except TelegramBadRequest as e:
            failed += 1
            err_msg = str(e).lower()
            if any(
                s in err_msg
                for s in ('chat not found', 'user not found', 'deactivated', 'bot was blocked', "can't initiate")
            ):
                blocked.append(chat_id)
            else:
                logger.warning(f'Напоминалка: ошибка для {chat_id}: {e}')
        except Exception as e:
            failed += 1
            logger.warning(f'Напоминалка: неожиданная ошибка для {chat_id}: {e}')

        # Сохраняем пачками
        if len(blocked) >= 20:
            await set_blocked_status_bulk(blocked)
            blocked.clear()

        if len(reminded) >= 50:
            await set_reminded_status_bulk(reminded)
            reminded.clear()

        await asyncio.sleep(delay)

    if blocked:
        await set_blocked_status_bulk(blocked)
    if reminded:
        await set_reminded_status_bulk(reminded)

    logger.info(
        f'Напоминалка завершена: успешно отправлено {sent}/{total}, заблокировали/недоступны: {failed}'
    )
    return sent, failed


async def reminder_scheduler_loop(bot: Bot) -> None:
    """Фоновый цикл планировщика: срабатывает каждый день в 15:15 по МСК."""
    logger.info('Фоновый планировщик напоминаний (15:15 МСК) инициализирован')
    while True:
        try:
            wait_seconds = get_seconds_until_next_reminder(15, 15)
            next_run = datetime.now(MSK_TZ) + timedelta(seconds=wait_seconds)
            logger.info(
                f'Напоминалка: следующий запуск в {next_run.strftime("%Y-%m-%d %H:%M:%S")} MSK (через {int(wait_seconds)} сек.)'
            )
            await asyncio.sleep(wait_seconds)

            today = datetime.now(MSK_TZ).strftime('%Y-%m-%d')
            key = f'reminder_sent:{today}'
            try:
                # Атомарный замок на сутки для исключения дублирования при перезапусках
                acquired = await redis.set(key, 1, ex=86400 * 2, nx=True)
                if not acquired:
                    logger.info(f'Напоминалка за {today} уже выполнялась, пропускаем.')
                    await asyncio.sleep(60)
                    continue
            except Exception as e:
                logger.warning(f'Ошибка проверки замка в Redis: {e}')

            logger.info('Запуск отправки напоминаний неактивным пользователям (15:15 МСК)...')
            await send_inactive_reminders(bot)

        except asyncio.CancelledError:
            logger.info('Фоновый планировщик напоминаний остановлен')
            break
        except Exception as e:
            logger.exception(f'Сбой в цикле напоминаний: {e}')
            await asyncio.sleep(60)


def start_reminder_scheduler(bot: Bot) -> asyncio.Task:
    """Запускает планировщик напоминаний как фоновую задачу asyncio."""
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(reminder_scheduler_loop(bot))
    return _scheduler_task


def stop_reminder_scheduler() -> None:
    """Останавливает планировщик напоминаний при завершении работы бота."""
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        _scheduler_task.cancel()
    _scheduler_task = None
