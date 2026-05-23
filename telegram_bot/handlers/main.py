from contextlib import suppress

from aiogram import Router, F
from aiogram import types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.fsm.context import FSMContext
from loguru import logger

from ..db import create_user, get_favorites
from ..config import START_GIF_URL
from ..keyboards import get_main_kb, get_favorites_kb, get_top_chart_kb, get_playlists_kb
from ..middlewares import YAMServiceMiddleware
from ..services import YAMService
from ..texts import MAIN_TEXT, NONE_FAVORITES_TEXT, FAVORITES_TEXT, TOP_CHAT_TEXT, PLAYLISTS_TEXT

router = Router()
router.message.middleware(YAMServiceMiddleware())
router.callback_query.middleware(YAMServiceMiddleware())


async def _safe_update_message(
    message: types.Message,
    text: str,
    reply_markup: types.InlineKeyboardMarkup
) -> None:
    """Безопасно обновляет текст/подпись сообщения с клавиатурой."""
    try:
        await message.edit_text(text=text, reply_markup=reply_markup)
        return
    except TelegramBadRequest as e:
        # У сообщений с анимацией/медиа нет text, только caption.
        if 'there is no text in the message to edit' not in str(e).lower():
            raise

    try:
        await message.edit_caption(caption=text, reply_markup=reply_markup)
    except TelegramBadRequest:
        # Если редактирование невозможно (например, старое сообщение), шлём новое.
        await message.answer(text=text, reply_markup=reply_markup)


@router.message(CommandStart())
async def command_start(msg: types.Message, state: FSMContext, command: CommandObject) -> None:
    """Обработчик команды /start."""
    logger.info(f'/start от {msg.from_user.id} ({msg.from_user.full_name})')
    await state.clear()
    await create_user(user_data=msg.from_user, source=command.args)
    try:
        await msg.answer_animation(
            animation=START_GIF_URL,
            caption=MAIN_TEXT,
            reply_markup=get_main_kb(),
            disable_notification=True
        )
    except TelegramBadRequest:
        await msg.answer(
            text=MAIN_TEXT,
            reply_markup=get_main_kb(),
            disable_notification=True
        )


@router.callback_query(lambda c: c.data == 'main:menu')
async def main_menu(cb: types.CallbackQuery) -> None:
    """Возврат в главное меню."""
    logger.debug(f'Пользователь {cb.from_user.id} вернулся в главное меню')
    await _safe_update_message(
        cb.message,
        text=MAIN_TEXT,
        reply_markup=get_main_kb()
    )
    await cb.answer()


@router.callback_query(lambda c: c.data == 'main:search')
async def search_button(cb: types.CallbackQuery) -> None:
    logger.debug(f'Пользователь {cb.from_user.id} нажал кнопку Поиск')
    await _safe_update_message(
        cb.message,
        text='👌 Чтобы начать просто напиши название или текст любой песни',
        reply_markup=get_main_kb()
    )
    await cb.answer()


@router.callback_query(lambda c: c.data == 'main:playlists')
async def selection_button(cb: types.CallbackQuery) -> None:
    logger.debug(f'Пользователь {cb.from_user.id} нажал кнопку Подборки')
    await _safe_update_message(cb.message, text=PLAYLISTS_TEXT, reply_markup=get_playlists_kb())
    await cb.answer()


@router.callback_query(lambda c: c.data == 'main:chart')
@router.callback_query(lambda c: c.data.startswith('chart'))
async def news_button(event: types.CallbackQuery, yam_service: YAMService) -> None:
    with suppress(TelegramBadRequest):
        await event.answer()
    
    if event.data.startswith('chart:'):
        page = int(event.data.split(':')[-1])
    else:
        page = 0
    
    logger.debug(f'Пользователь {event.from_user.id} запросил Топ-чарт (страница {page})')
    chart = await yam_service.get_top_chart(page)
    await _safe_update_message(event.message, text=TOP_CHAT_TEXT, reply_markup=get_top_chart_kb(chart))


@router.callback_query(lambda c: c.data == 'main:favorites')
async def favorites_button_callback(cb: types.CallbackQuery) -> None:
    """Обработчик кнопки Избранное через callback."""
    logger.debug(f'Пользователь {cb.from_user.id} нажал Избранное')
    await cb.answer()
    favorites = await get_favorites(cb.from_user.id)
    if not favorites:
        await _safe_update_message(cb.message, text=NONE_FAVORITES_TEXT, reply_markup=get_main_kb())
        return

    favorites_data = {'results': favorites}
    await _safe_update_message(
        cb.message,
        text=FAVORITES_TEXT,
        reply_markup=get_favorites_kb(data=favorites_data, chat_id=cb.from_user.id)
    )


@router.message(Command('favorites'))
async def favorites_button_message(msg: types.Message) -> None:
    """Обработчик команды /favorites."""
    logger.debug(f'Пользователь {msg.from_user.id} использовал команду /favorites')
    favorites = await get_favorites(msg.from_user.id)
    if not favorites:
        await msg.answer(text=NONE_FAVORITES_TEXT, reply_markup=get_main_kb())
        return

    favorites_data = {'results': favorites}
    await msg.answer(
        text=FAVORITES_TEXT,
        reply_markup=get_favorites_kb(data=favorites_data, chat_id=msg.from_user.id)
    )


@router.message(F.voice)
@router.message(F.sticker)
@router.message(F.document)
@router.message(F.location)
@router.message(F.photo)
@router.message(F.video)
async def handle_another(msg: types.Message) -> None:
    logger.debug(f'Удаляем сообщение {msg.message_id} от {msg.from_user.id} (voice/sticker)')
    await msg.delete()
