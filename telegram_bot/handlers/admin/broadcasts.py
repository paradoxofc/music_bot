import asyncio
from typing import Any

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from loguru import logger

from .main import router
from ...constants import EventType
from ...db import (
    create_broadcast,
    get_broadcast,
    get_broadcasts_summary,
    list_broadcasts,
    send_event,
    set_broadcast_buttons,
    update_broadcast,
    get_db,
    release_db,
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
async def retrieve(cb: types.CallbackQuery) -> None:
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
async def send_broadcast(cb: types.CallbackQuery) -> None:
    _, _, target, broadcast_id = cb.data.split(':', 3)
    broadcast = await get_broadcast(broadcast_id)
    if not broadcast:
        await cb.answer('Рассылка не найдена', show_alert=True)
        return

    if broadcast.get('is_sent'):
        await cb.answer('Рассылка уже была отправлена', show_alert=True)
        return

    if target == 'all':
        await cb.message.edit_text(
            text='<b>❓ Вы уверены, что хотите запустить рассылку?</b>',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[
                    types.InlineKeyboardButton(text='Да', callback_data=f'broadcast:action:confirm:{broadcast_id}'),
                    types.InlineKeyboardButton(text='Нет', callback_data=f'broadcast:retrieve:{broadcast_id}')
                ]]
            )
        )
        await cb.answer()
        return

    await _send_broadcast_message(cb.bot, cb.from_user.id, broadcast)
    await cb.answer(text='Отправлено вам', show_alert=True)


@router.callback_query(lambda c: c.data.startswith('broadcast:action:confirm'))
async def send_to_all_confirm(cb: types.CallbackQuery) -> None:
    broadcast_id = cb.data.split(':')[-1]
    broadcast = await get_broadcast(broadcast_id)
    if not broadcast:
        await cb.answer('Рассылка не найдена', show_alert=True)
        return
    if broadcast.get('is_sent'):
        await cb.answer('Рассылка уже была отправлена', show_alert=True)
        return

    sent = 0
    failed = 0
    conn = await get_db()
    try:
        users = await conn.fetch("SELECT chat_id FROM users WHERE is_active = true")
    finally:
        await release_db(conn)

    for row in users:
        chat_id = row['chat_id']
        try:
            await _send_broadcast_message(cb.bot, chat_id, broadcast)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            logger.warning(f'Не удалось отправить рассылку {broadcast_id} пользователю {chat_id}: {e}')

    await update_broadcast(broadcast_id, {'is_sent': True})
    if sent > 0:
        await send_event(event_type=EventType.BROADCAST, chat_id=cb.from_user.id)
    await cb.answer(text=f'Готово: отправлено {sent}, ошибок {failed}', show_alert=True)
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
