import asyncio
import contextlib
from typing import Any

from aiogram import F, types
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from loguru import logger

from .main import router
from ...config import BROADCAST_RATE
from ...constants import EventType
from ...db import (
    create_broadcast,
    get_active_users_count,
    get_broadcast,
    get_broadcasts_summary,
    iter_active_user_ids,
    list_broadcasts,
    send_event,
    set_blocked_status_bulk,
    set_broadcast_buttons,
    try_start_broadcast,
    update_broadcast,
)
from ...keyboards import back_to_admin_button, get_admin_main_kb, get_broadcast_retrieve_kb, get_broadcasts_kb
from ...validators import is_safe_http_url
from ...texts import (
    ADMIN_MAIN_TEXT,
    BROADCASTS_MAIN_TEXT,
    FILE_INFO_ERROR_TEXT,
    FILE_INFO_RESULT_TEXT,
    GET_FILE_INFO_TEXT,
    get_broadcast_retrieve_text,
)


class GetFileInfo(StatesGroup):
    waiting_media = State()


class EditBroadcast(StatesGroup):
    waiting_name = State()
    waiting_text = State()
    waiting_media = State()
    waiting_buttons = State()
    waiting_limit = State()



def _build_url_buttons(buttons: list[dict]) -> types.InlineKeyboardMarkup | None:
    if not buttons:
        return None
    rows = [[types.InlineKeyboardButton(text=b['text'], url=b['url'])] for b in buttons]
    return types.InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_broadcast_message(bot: Any, chat_id: int, broadcast: dict) -> None:
    reply_markup = _build_url_buttons(broadcast.get('buttons', []))
    message = (broadcast.get('message') or '').strip()
    file_type = broadcast.get('file_type')
    file_id = broadcast.get('file_id')
    caption = message or None

    if file_type == 'sendPhoto' and file_id:
        await bot.send_photo(chat_id=chat_id, photo=file_id, caption=caption, reply_markup=reply_markup)
    elif file_type == 'sendAnimation' and file_id:
        await bot.send_animation(chat_id=chat_id, animation=file_id, caption=caption, reply_markup=reply_markup)
    elif file_type == 'sendVideo' and file_id:
        await bot.send_video(chat_id=chat_id, video=file_id, caption=caption, reply_markup=reply_markup)
    else:
        safe_text = message or 'Без текста'
        await bot.send_message(chat_id=chat_id, text=safe_text, reply_markup=reply_markup)


@router.callback_query(lambda c: c.data.startswith('broadcast:list'))
async def broadcasts_list(cb: types.CallbackQuery) -> None:
    await cb.answer()
    page_raw = cb.data.split(':')[-1]
    page = int(page_raw) if page_raw.isdigit() else 1
    broadcasts = await list_broadcasts(page)
    summary = await get_broadcasts_summary()
    text = BROADCASTS_MAIN_TEXT.format(
        total=summary['total'],
        sent=summary['sent'],
    )
    await cb.message.edit_text(text=text, reply_markup=get_broadcasts_kb(broadcasts))


@router.callback_query(lambda c: c.data == 'broadcast:add')
async def add_broadcast(cb: types.CallbackQuery) -> None:
    created = await create_broadcast()
    await cb.answer('Рассылка создана')
    await cb.message.edit_text(
        text=get_broadcast_retrieve_text(created),
        reply_markup=get_broadcast_retrieve_kb(str(created['id']))
    )


@router.callback_query(lambda c: c.data.startswith('broadcast:retrieve'))
async def retrieve(cb: types.CallbackQuery, state: FSMContext | None = None) -> None:
    if state:
        await state.clear()
    await cb.answer()
    broadcast_id = cb.data.split(':')[-1]
    broadcast_data = await get_broadcast(broadcast_id)
    if not broadcast_data:
        await cb.message.edit_text(
            text='Рассылка не найдена.',
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[back_to_admin_button]])
        )
        return
    await cb.message.edit_text(
        text=get_broadcast_retrieve_text(broadcast_data),
        reply_markup=get_broadcast_retrieve_kb(broadcast_id)
    )



@router.callback_query(lambda c: c.data.startswith('broadcast:edit_name'))
async def edit_broadcast_name(cb: types.CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.set_state(EditBroadcast.waiting_name)
    await state.update_data(broadcast_id=cb.data.split(':')[-1])
    await cb.message.edit_text(
        text='📝 Введите новое <b>название</b> рассылки:',
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[back_to_admin_button]])
    )


@router.message(EditBroadcast.waiting_name)
async def edit_broadcast_name_receive(msg: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    broadcast_id = data.get('broadcast_id')
    name = msg.text.strip() if msg.text else ''
    if not name:
        await msg.answer('Название не может быть пустым. Попробуйте снова.')
        return
    await update_broadcast(broadcast_id, {'name': name})
    await state.clear()
    broadcast_data = await get_broadcast(broadcast_id)
    await msg.answer(text=get_broadcast_retrieve_text(broadcast_data), reply_markup=get_broadcast_retrieve_kb(str(broadcast_id)))


@router.callback_query(lambda c: c.data.startswith('broadcast:edit_text'))
async def edit_broadcast_text(cb: types.CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.set_state(EditBroadcast.waiting_text)
    await state.update_data(broadcast_id=cb.data.split(':')[-1])
    await cb.message.edit_text(
        text='💬 Отправьте новый <b>текст</b> рассылки:',
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[back_to_admin_button]])
    )


@router.message(EditBroadcast.waiting_text)
async def edit_broadcast_text_receive(msg: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    broadcast_id = data.get('broadcast_id')
    text = msg.html_text or msg.text or ''
    await update_broadcast(broadcast_id, {'message': text})
    await state.clear()
    broadcast_data = await get_broadcast(broadcast_id)
    await msg.answer(text=get_broadcast_retrieve_text(broadcast_data), reply_markup=get_broadcast_retrieve_kb(str(broadcast_id)))


@router.callback_query(lambda c: c.data.startswith('broadcast:edit_media'))
async def edit_broadcast_media(cb: types.CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.set_state(EditBroadcast.waiting_media)
    await state.update_data(broadcast_id=cb.data.split(':')[-1])
    await cb.message.edit_text(
        text='📎 Отправьте фото / GIF / видео. Чтобы удалить вложение, отправьте «Без вложения».',
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[back_to_admin_button]])
    )


@router.message(EditBroadcast.waiting_media, F.photo | F.animation | F.video | F.text)
async def edit_broadcast_media_receive(msg: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    broadcast_id = data.get('broadcast_id')
    payload = {}
    if msg.text and msg.text.strip().lower() in {'без вложения', 'none', 'no'}:
        payload = {'file_type': 'sendMessage', 'file_id': None}
    elif msg.photo:
        payload = {'file_type': 'sendPhoto', 'file_id': msg.photo[-1].file_id}
    elif msg.animation:
        payload = {'file_type': 'sendAnimation', 'file_id': msg.animation.file_id}
    elif msg.video:
        payload = {'file_type': 'sendVideo', 'file_id': msg.video.file_id}
    else:
        await msg.answer('Не удалось определить тип. Пришлите фото, GIF или видео.')
        return
    await update_broadcast(broadcast_id, payload)
    await state.clear()
    broadcast_data = await get_broadcast(broadcast_id)
    await msg.answer(text=get_broadcast_retrieve_text(broadcast_data), reply_markup=get_broadcast_retrieve_kb(str(broadcast_id)))


@router.callback_query(lambda c: c.data.startswith('broadcast:edit_buttons'))
async def edit_broadcast_buttons(cb: types.CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.set_state(EditBroadcast.waiting_buttons)
    await state.update_data(broadcast_id=cb.data.split(':')[-1])
    await cb.message.edit_text(
        text=(
            "🔘 <b>Изменить кнопки</b>\n\n"
            "Отправьте список кнопок, по одной на строку в формате:\n"
            "<code>Текст — https://example.com</code>\n\n"
            "Чтобы удалить все кнопки, отправьте «нет»."
        ),
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[back_to_admin_button]])
    )


@router.message(EditBroadcast.waiting_buttons)
async def edit_broadcast_buttons_receive(msg: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    broadcast_id = data.get('broadcast_id')
    text = msg.text or ''
    buttons: list[dict] = []
    invalid_lines = []
    if text.strip().lower() not in {'нет', 'no', 'none'}:
        for line in text.splitlines():
            if '—' in line:
                left, right = line.split('—', 1)
            elif '-' in line:
                left, right = line.split('-', 1)
            else:
                continue
            btn_text = left.strip()
            btn_url = right.strip()
            if btn_text and btn_url and is_safe_http_url(btn_url):
                buttons.append({'text': btn_text, 'url': btn_url.strip()})
            elif btn_text or btn_url:
                invalid_lines.append(line)
    if invalid_lines:
        await msg.answer(
            "<b>⚠️ Некорректные URL:</b>\n" + "\n".join(invalid_lines),
            parse_mode='HTML'
        )
        return
    await set_broadcast_buttons(broadcast_id, buttons)
    await state.clear()
    broadcast_data = await get_broadcast(broadcast_id)
    await msg.answer(text=get_broadcast_retrieve_text(broadcast_data), reply_markup=get_broadcast_retrieve_kb(str(broadcast_id)))


@router.callback_query(lambda c: c.data.startswith('broadcast:send'))
async def send_broadcast(cb: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    _, _, target, broadcast_id = cb.data.split(':', 3)
    broadcast = await get_broadcast(broadcast_id)
    if not broadcast:
        await cb.answer('Рассылка не найдена', show_alert=True)
        return

    if broadcast.get('is_sent'):
        await cb.answer('Рассылка уже была отправлена', show_alert=True)
        return

    if target == 'all':
        active_count = await get_active_users_count()
        if active_count == 0:
            await cb.answer('В базе нет активных пользователей для рассылки', show_alert=True)
            return

        text = (
            f'🚀 <b>Запуск рассылки #{broadcast_id}</b>\n\n'
            f'Доступно активных пользователей: <b>{active_count}</b>\n'
            f'<i>(пользователи, заблокировавшие бота, исключены автоматически)</i>\n\n'
            f'Выберите режим отправки:'
        )
        kb = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text=f'👥 Всем активным ({active_count})',
                        callback_data=f'broadcast:confirm:all:{broadcast_id}'
                    )
                ],
                [
                    types.InlineKeyboardButton(
                        text='🎯 Указать количество юзеров',
                        callback_data=f'broadcast:ask_limit:{broadcast_id}'
                    )
                ],
                [
                    types.InlineKeyboardButton(
                        text='◀️ Назад',
                        callback_data=f'broadcast:retrieve:{broadcast_id}'
                    )
                ]
            ]
        )
        await cb.message.edit_text(text=text, reply_markup=kb)
        await cb.answer()
        return

    await _send_broadcast_message(cb.bot, cb.from_user.id, broadcast)
    await cb.answer(text='Отправлено вам', show_alert=True)


@router.callback_query(lambda c: c.data.startswith('broadcast:confirm:all'))
async def broadcast_confirm_all(cb: types.CallbackQuery) -> None:
    broadcast_id = cb.data.split(':')[-1]
    active_count = await get_active_users_count()
    text = (
        f'<b>❓ Подтверждение запуска рассылки</b>\n\n'
        f'Рассылка: <b>#{broadcast_id}</b>\n'
        f'Получатели: <b>все активные пользователи ({active_count})</b>\n'
        f'<i>(заблокировавшие бота пользователи не получат сообщение)</i>\n\n'
        f'Запустить рассылку?'
    )
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text='✅ Да, запустить',
                    callback_data=f'broadcast:run:all:{broadcast_id}'
                ),
                types.InlineKeyboardButton(
                    text='❌ Отмена',
                    callback_data=f'broadcast:retrieve:{broadcast_id}'
                )
            ]
        ]
    )
    await cb.message.edit_text(text=text, reply_markup=kb)
    await cb.answer()


@router.callback_query(lambda c: c.data.startswith('broadcast:ask_limit'))
async def broadcast_ask_limit(cb: types.CallbackQuery, state: FSMContext) -> None:
    broadcast_id = cb.data.split(':')[-1]
    active_count = await get_active_users_count()
    await state.set_state(EditBroadcast.waiting_limit)
    await state.update_data(broadcast_id=broadcast_id, active_count=active_count)
    await cb.answer()

    text = (
        f'🎯 <b>Укажите количество пользователей</b>\n\n'
        f'Доступно активных пользователей: <b>{active_count}</b>\n'
        f'<i>(пользователи, заблокировавшие бота, исключены)</i>\n\n'
        f'Отправьте желаемое число сообщением (например, <code>100</code> или <code>500</code>):'
    )
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text='◀️ Отмена',
                    callback_data=f'broadcast:retrieve:{broadcast_id}'
                )
            ]
        ]
    )
    await cb.message.edit_text(text=text, reply_markup=kb)


@router.message(EditBroadcast.waiting_limit, F.text)
async def broadcast_limit_receive(msg: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    broadcast_id = data.get('broadcast_id')
    raw_text = (msg.text or '').strip()

    if not raw_text.isdigit() or int(raw_text) <= 0:
        await msg.answer(
            '⚠️ Пожалуйста, введите положительное целое число (например, <code>100</code>):',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text='◀️ Отмена',
                            callback_data=f'broadcast:retrieve:{broadcast_id}'
                        )
                    ]
                ]
            )
        )
        return

    limit = int(raw_text)
    active_count = await get_active_users_count()
    warning_text = ''
    if limit > active_count:
        warning_text = (
            f'ℹ️ В базе только <b>{active_count}</b> активных пользователей.\n'
            f'Количество скорректировано до <b>{active_count}</b>.\n\n'
        )
        limit = active_count

    await state.clear()

    text = (
        f'{warning_text}'
        f'<b>❓ Подтверждение запуска рассылки</b>\n\n'
        f'Рассылка: <b>#{broadcast_id}</b>\n'
        f'Количество получателей: <b>{limit}</b> активных пользователей\n'
        f'<i>(только пользователи, не заблокировавшие бота)</i>\n\n'
        f'Запустить рассылку?'
    )
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text='✅ Да, запустить',
                    callback_data=f'broadcast:run:{limit}:{broadcast_id}'
                ),
                types.InlineKeyboardButton(
                    text='❌ Отмена',
                    callback_data=f'broadcast:retrieve:{broadcast_id}'
                )
            ]
        ]
    )
    await msg.answer(text=text, reply_markup=kb)


async def _run_broadcast(
    bot: Any,
    admin_chat_id: int,
    broadcast: dict,
    limit: int | None = None,
) -> None:
    """Фоновая отправка рассылки активным пользователям."""
    broadcast_id = broadcast['id']
    sent = 0
    failed = 0
    blocked: list[int] = []
    total_active = await get_active_users_count()
    target_count = min(total_active, limit) if limit else total_active
    delay = 1 / max(1, BROADCAST_RATE)

    limit_desc = f'{target_count} пользователей' if limit else f'всем ({total_active})'
    status_message = await bot.send_message(
        chat_id=admin_chat_id,
        text=f'🚀 Рассылка #{broadcast_id} запущена. Цель: {limit_desc}.',
    )

    async for chat_id in iter_active_user_ids():
        if limit is not None and sent >= limit:
            break

        try:
            await _send_broadcast_message(bot, chat_id, broadcast)
            sent += 1
        except TelegramRetryAfter as e:
            logger.warning(f'Рассылка {broadcast_id}: flood control, пауза {e.retry_after}s')
            await asyncio.sleep(e.retry_after)
            try:
                await _send_broadcast_message(bot, chat_id, broadcast)
                sent += 1
            except (TelegramForbiddenError, TelegramBadRequest) as retry_err:
                failed += 1
                err_msg = str(retry_err).lower()
                if isinstance(retry_err, TelegramForbiddenError) or any(
                    s in err_msg for s in ('chat not found', 'user not found', 'deactivated', 'bot was blocked', "can't initiate")
                ):
                    blocked.append(chat_id)
            except Exception as retry_error:
                failed += 1
                logger.warning(
                    f'Рассылка {broadcast_id}: повтор для {chat_id} не удался: {retry_error}'
                )
        except TelegramForbiddenError:
            # Пользователь заблокировал бота — помечаем неактивным
            failed += 1
            blocked.append(chat_id)
        except TelegramBadRequest as e:
            failed += 1
            err_msg = str(e).lower()
            if any(
                s in err_msg
                for s in ('chat not found', 'user not found', 'deactivated', 'bot was blocked', "can't initiate conversation")
            ):
                blocked.append(chat_id)
            else:
                logger.warning(f'Рассылка {broadcast_id}: ошибка для {chat_id}: {e}')
        except Exception as e:
            failed += 1
            logger.warning(f'Рассылка {broadcast_id}: ошибка для {chat_id}: {e}')

        # Сохраняем заблокированных пользователей пачками по 20
        if len(blocked) >= 20:
            await set_blocked_status_bulk(blocked)
            blocked.clear()

        # Обновляем статус каждые 50 отправок или при завершении
        if (sent + failed) % 50 == 0 or (limit and sent >= limit):
            with contextlib.suppress(Exception):
                await status_message.edit_text(
                    f'🚀 Рассылка #{broadcast_id} в процессе...\n\n'
                    f'🎯 Цель: <b>{target_count}</b>\n'
                    f'✅ Доставлено: <b>{sent}/{target_count}</b>\n'
                    f'🚫 Не доставлено (блок бота): <b>{failed}</b>'
                )

        await asyncio.sleep(delay)

    if blocked:
        await set_blocked_status_bulk(blocked)

    if sent > 0:
        await send_event(event_type=EventType.BROADCAST, chat_id=admin_chat_id)

    logger.info(f'Рассылка {broadcast_id} завершена: отправлено {sent}, ошибок/блокировок {failed}')
    with contextlib.suppress(Exception):
        await status_message.edit_text(
            f'✅ <b>Рассылка #{broadcast_id} завершена!</b>\n\n'
            f'📨 Доставлено активным пользователям: <b>{sent}</b>'
            + (f' из {target_count}' if limit else '')
            + f'\n🚫 Заблокировали бота / не доставлено: <b>{failed}</b>'
        )


@router.callback_query(lambda c: c.data.startswith(('broadcast:run:', 'broadcast:action:confirm:')))
async def run_broadcast_callback(cb: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    parts = cb.data.split(':')
    if cb.data.startswith('broadcast:run:'):
        limit_str = parts[2]
        broadcast_id = parts[3]
    else:
        limit_str = 'all'
        broadcast_id = parts[-1]

    broadcast = await get_broadcast(broadcast_id)
    if not broadcast:
        await cb.answer('Рассылка не найдена', show_alert=True)
        return

    # Атомарно помечаем рассылку запущенной — защита от параллельного запуска
    if not await try_start_broadcast(broadcast_id):
        await cb.answer('Рассылка уже была отправлена', show_alert=True)
        return

    limit = None if limit_str == 'all' else int(limit_str)
    await cb.answer('Рассылка запущена', show_alert=True)
    asyncio.create_task(_run_broadcast(cb.bot, cb.from_user.id, broadcast, limit=limit))

    await cb.message.edit_text(
        text=ADMIN_MAIN_TEXT.format(name=cb.from_user.full_name),
        reply_markup=get_admin_main_kb()
    )


@router.callback_query(lambda c: c.data == 'get_file_info')
async def get_file_info(cb: types.CallbackQuery, state: FSMContext) -> None:
    await state.set_state(GetFileInfo.waiting_media)
    await cb.answer()
    await cb.message.edit_text(
        text=GET_FILE_INFO_TEXT,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[back_to_admin_button]])
    )


@router.message(GetFileInfo.waiting_media, F.photo | F.animation | F.video)
async def admin_receive_media(msg: types.Message, state: FSMContext) -> None:
    file_id = None
    file_type = None
    if msg.photo:
        file_id = msg.photo[-1].file_id
        file_type = 'Фото'
    elif msg.animation:
        file_id = msg.animation.file_id
        file_type = 'Анимация'
    elif msg.video:
        file_id = msg.video.file_id
        file_type = 'Видео'
    if not file_id:
        await msg.answer('Не удалось определить file_id. Пришли другое вложение.')
        return
    await msg.answer(
        text=FILE_INFO_RESULT_TEXT.format(file_type=file_type, file_id=file_id),
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[back_to_admin_button]])
    )
    await state.clear()


@router.message(GetFileInfo.waiting_media)
async def admin_waiting_wrong_content(msg: types.Message) -> None:
    await msg.answer(
        text=FILE_INFO_ERROR_TEXT,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[back_to_admin_button]])
    )
