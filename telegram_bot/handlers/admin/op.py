from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from loguru import logger

from .main import router
from ...db import (
    activate_op_setup,
    create_op_setup,
    deactivate_op_setup,
    get_op_setup,
    list_op_setups,
    set_op_channels,
    update_op_setup,
)
from ...keyboards import (
    back_to_admin_button,
    get_op_list_kb,
    get_op_retrieve_kb,
)
from ...keyboards.op import get_op_subscribe_kb
from ...texts import OP_MAIN_TEXT, get_op_retrieve_text
from ...services.op_check import validate_bot_can_check_channels
from ...validators import parse_op_channel_line


class EditOpSetup(StatesGroup):
    waiting_name = State()
    waiting_text = State()
    waiting_channels = State()


DEFAULT_OP_MESSAGE = (
    '<b>📌 Подпишитесь на каналы</b>\n\n'
    'Чтобы пользоваться ботом, подпишитесь на указанные каналы и нажмите '
    '<b>«Проверить подписку»</b>.'
)

FSM_EXPIRED_TEXT = 'Сессия редактирования истекла. Откройте 📌 ОП в админке снова.'


async def _require_op_setup_id(state: FSMContext, msg: types.Message) -> str | None:
    data = await state.get_data()
    op_setup_id = data.get('op_setup_id')
    if not op_setup_id:
        await state.clear()
        await msg.answer(FSM_EXPIRED_TEXT)
        return None
    return str(op_setup_id)


@router.callback_query(lambda c: c.data.startswith('op:list'))
async def op_list(cb: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.answer()
    page_raw = cb.data.split(':')[-1]
    page = int(page_raw) if page_raw.isdigit() else 1
    setups = await list_op_setups(page)
    await cb.message.edit_text(text=OP_MAIN_TEXT, reply_markup=get_op_list_kb(setups))


@router.callback_query(lambda c: c.data == 'op:add')
async def op_add(cb: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    created = await create_op_setup()
    await cb.answer('ОП создана')
    await cb.message.edit_text(
        text=get_op_retrieve_text(created),
        reply_markup=get_op_retrieve_kb(str(created['id']), bool(created.get('is_active'))),
    )


@router.callback_query(lambda c: c.data.startswith('op:retrieve'))
async def op_retrieve(cb: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.answer()
    op_setup_id = cb.data.split(':')[-1]
    op_data = await get_op_setup(op_setup_id)
    if not op_data:
        await cb.message.edit_text(
            text='ОП не найдена.',
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[back_to_admin_button]]),
        )
        return
    await cb.message.edit_text(
        text=get_op_retrieve_text(op_data),
        reply_markup=get_op_retrieve_kb(op_setup_id, bool(op_data.get('is_active'))),
    )


@router.callback_query(lambda c: c.data.startswith('op:toggle'))
async def op_toggle(cb: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    parts = cb.data.split(':')
    action, op_setup_id = parts[2], parts[3]
    op_data = await get_op_setup(op_setup_id)
    if not op_data:
        await cb.answer('ОП не найдена', show_alert=True)
        return

    if action == 'on':
        if not op_data.get('channels'):
            await cb.answer('Сначала добавьте хотя бы один канал', show_alert=True)
            return
        try:
            validation_errors = await validate_bot_can_check_channels(cb.bot, op_data['channels'])
        except Exception as e:
            logger.exception('ОП: ошибка валидации каналов при включении')
            await cb.answer('Ошибка проверки каналов', show_alert=True)
            await cb.message.answer(f'<b>⚠️ Ошибка:</b> {e}')
            return
        if validation_errors:
            await cb.answer('Бот не может проверять каналы', show_alert=True)
            await cb.message.answer(
                '<b>⚠️ Нельзя включить ОП:</b>\n' + '\n'.join(f'• {e}' for e in validation_errors),
            )
            return
        await activate_op_setup(op_setup_id)
        await cb.answer('ОП включена')
    else:
        await deactivate_op_setup(op_setup_id)
        await cb.answer('ОП выключена')

    op_data = await get_op_setup(op_setup_id)
    await cb.message.edit_text(
        text=get_op_retrieve_text(op_data),
        reply_markup=get_op_retrieve_kb(op_setup_id, bool(op_data.get('is_active'))),
    )


@router.callback_query(lambda c: c.data.startswith('op:preview'))
async def op_preview(cb: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    op_setup_id = cb.data.split(':')[-1]
    op_data = await get_op_setup(op_setup_id)
    if not op_data:
        await cb.answer('ОП не найдена', show_alert=True)
        return
    if not op_data.get('channels'):
        await cb.answer('Добавьте каналы для превью', show_alert=True)
        return

    text = (op_data.get('message') or '').strip() or DEFAULT_OP_MESSAGE
    await cb.bot.send_message(
        chat_id=cb.from_user.id,
        text=text,
        reply_markup=get_op_subscribe_kb(op_data['channels']),
    )
    await cb.answer('Превью отправлено')


@router.callback_query(lambda c: c.data.startswith('op:edit_name'))
async def op_edit_name(cb: types.CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.set_state(EditOpSetup.waiting_name)
    await state.update_data(op_setup_id=cb.data.split(':')[-1])
    await cb.message.edit_text(
        text='📝 Введите новое <b>название</b> ОП:',
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[back_to_admin_button]]),
    )


@router.message(EditOpSetup.waiting_name)
async def op_edit_name_receive(msg: types.Message, state: FSMContext) -> None:
    op_setup_id = await _require_op_setup_id(state, msg)
    if not op_setup_id:
        return
    name = msg.text.strip() if msg.text else ''
    if not name:
        await msg.answer('Название не может быть пустым. Попробуйте снова.')
        return
    await update_op_setup(op_setup_id, {'name': name})
    await state.clear()
    op_data = await get_op_setup(op_setup_id)
    if not op_data:
        await msg.answer('ОП не найдена.')
        return
    await msg.answer(
        text=get_op_retrieve_text(op_data),
        reply_markup=get_op_retrieve_kb(str(op_setup_id), bool(op_data.get('is_active'))),
    )


@router.callback_query(lambda c: c.data.startswith('op:edit_text'))
async def op_edit_text(cb: types.CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.set_state(EditOpSetup.waiting_text)
    await state.update_data(op_setup_id=cb.data.split(':')[-1])
    await cb.message.edit_text(
        text='💬 Отправьте <b>текст</b>, который увидит пользователь без подписки:',
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[back_to_admin_button]]),
    )


@router.message(EditOpSetup.waiting_text)
async def op_edit_text_receive(msg: types.Message, state: FSMContext) -> None:
    op_setup_id = await _require_op_setup_id(state, msg)
    if not op_setup_id:
        return
    text = msg.html_text or msg.text or ''
    await update_op_setup(op_setup_id, {'message': text})
    await state.clear()
    op_data = await get_op_setup(op_setup_id)
    if not op_data:
        await msg.answer('ОП не найдена.')
        return
    await msg.answer(
        text=get_op_retrieve_text(op_data),
        reply_markup=get_op_retrieve_kb(str(op_setup_id), bool(op_data.get('is_active'))),
    )


@router.callback_query(lambda c: c.data.startswith('op:edit_channels'))
async def op_edit_channels(cb: types.CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.set_state(EditOpSetup.waiting_channels)
    await state.update_data(op_setup_id=cb.data.split(':')[-1])
    await cb.message.edit_text(
        text=(
            '📢 <b>Изменить каналы</b>\n\n'
            'По одной строке в формате:\n'
            '<code>Текст кнопки — @channel_username</code>\n'
            '<code>Текст кнопки — https://t.me/channel</code>\n'
            '<code>Текст кнопки — -1001234567890</code>\n\n'
            'Чтобы удалить все каналы, отправьте «нет».\n\n'
            '<i>Бот должен быть админом в каждом канале.</i>'
        ),
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[back_to_admin_button]]),
    )


@router.message(EditOpSetup.waiting_channels)
async def op_edit_channels_receive(msg: types.Message, state: FSMContext) -> None:
    op_setup_id = await _require_op_setup_id(state, msg)
    if not op_setup_id:
        return
    text = msg.text or ''
    channels: list[dict] = []
    invalid_lines = []

    if text.strip().lower() not in {'нет', 'no', 'none'}:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            parsed = parse_op_channel_line(line)
            if parsed:
                channels.append(parsed)
            else:
                invalid_lines.append(line)

    if invalid_lines:
        await msg.answer(
            '<b>⚠️ Не удалось разобрать строки:</b>\n' + '\n'.join(invalid_lines),
            parse_mode='HTML',
        )
        return

    await set_op_channels(op_setup_id, channels)
    await state.clear()
    op_data = await get_op_setup(op_setup_id)
    if not op_data:
        await msg.answer('ОП не найдена.')
        return

    reply = get_op_retrieve_text(op_data)
    if channels:
        try:
            validation_errors = await validate_bot_can_check_channels(msg.bot, channels)
        except Exception as e:
            logger.exception('ОП: ошибка валидации каналов после сохранения')
            validation_errors = [str(e)]
        if validation_errors:
            reply += '\n\n<b>⚠️ Проверка подписки не сработает:</b>\n' + '\n'.join(
                f'• {e}' for e in validation_errors
            )

    await msg.answer(
        text=reply,
        reply_markup=get_op_retrieve_kb(str(op_setup_id), bool(op_data.get('is_active'))),
    )
