from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from loguru import logger

from ..db import send_event
from ..keyboards import get_search_kb
from ..middlewares import YAMServiceMiddleware
from ..services import YAMService

router = Router()
router.message.middleware(YAMServiceMiddleware())
router.callback_query.middleware(YAMServiceMiddleware())


class SearchState(StatesGroup):
    waiting_for_query = State()


@router.message(Command('search'))
async def search_command(msg: types.Message, state: FSMContext) -> None:
    """Обработчик команды /search."""
    await state.set_state(SearchState.waiting_for_query)
    await msg.answer('Введите название песни или исполнителя:')


@router.message(SearchState.waiting_for_query)
async def search_query(msg: types.Message, state: FSMContext, yam_service: YAMService) -> None:
    """Поиск треков по запросу (после команды /search)."""
    await _do_search(msg, msg.text.strip(), yam_service)
    await state.clear()


@router.message(F.text)
async def search_free_text(msg: types.Message, yam_service: YAMService) -> None:
    """Поиск треков по любому текстовому сообщению."""
    await _do_search(msg, msg.text.strip(), yam_service)


async def _do_search(msg: types.Message, query: str, yam_service: YAMService) -> None:
    """Общая логика поиска."""
    if not query:
        await msg.answer('Пожалуйста, введите текст для поиска.')
        return

    logger.info(f'Пользователь {msg.from_user.id} ищет: {query!r}')
    await send_event(event_type=1, chat_id=msg.from_user.id)

    searching_msg = await msg.answer('🔍 Ищу...')

    try:
        results = await yam_service.search(query)

        if not results:
            await searching_msg.delete()
            await msg.answer('😔 Ничего не найдено. Попробуйте изменить запрос.')
            return

        await searching_msg.delete()

        kb = get_search_kb(results)
        if not kb:
            await msg.answer('😔 Ничего не найдено. Попробуйте изменить запрос.')
            return

        await msg.answer(
            f'🔍 Результаты поиска по запросу "{query}":',
            reply_markup=kb
        )

    except Exception as e:
        logger.exception(f'Ошибка при поиске: {e}')
        await searching_msg.delete()
        await msg.answer('❌ Произошла ошибка при поиске. Попробуйте позже.')


@router.callback_query(lambda c: c.data.startswith('search:'))
async def search_callback(cb: types.CallbackQuery, yam_service: YAMService) -> None:
    """Обработчик пагинации поиска."""
    payload, page_raw = cb.data.rsplit(':', 1)
    query = payload.removeprefix('search:')
    try:
        page = int(page_raw)
    except ValueError:
        await cb.answer('Некорректная страница')
        return
    
    if not query:
        await cb.answer('Ошибка: не найден запрос')
        return
    
    try:
        results = await yam_service.search(query, page)
        if not results:
            await cb.answer('Результаты не найдены')
            return
        
        kb = get_search_kb(results)
        await cb.message.edit_reply_markup(reply_markup=kb)
        await cb.answer()
    except Exception as e:
        logger.exception(f'Ошибка при пагинации поиска: {e}')
        await cb.answer('Произошла ошибка')


@router.callback_query(lambda c: c.data.startswith('artist_search:'))
async def artist_search_callback(cb: types.CallbackQuery, yam_service: YAMService) -> None:
    """Обработчик поиска треков по артисту."""
    try:
        _, artist_id, page_raw = cb.data.split(':', 2)
        page = int(page_raw)
    except (ValueError, IndexError):
        await cb.answer('Некорректные данные кнопки')
        return

    try:
        results = await yam_service.search_by_artist(artist_id=artist_id, page=page)
        if not results or not results.get('tracks'):
            await cb.answer('Треки исполнителя не найдены')
            return

        kb = get_search_kb(results, is_artist_search=True)
        # Если callback пришёл из сообщения с аудио/медиа, открываем список отдельным сообщением,
        # чтобы удаление списка не удаляло сам трек.
        if cb.message.audio or cb.message.video or cb.message.animation or cb.message.photo:
            await cb.message.answer('🔎 Все треки исполнителя:', reply_markup=kb)
        else:
            await cb.message.edit_reply_markup(reply_markup=kb)
        await cb.answer()
    except Exception as e:
        logger.exception(f'Ошибка при поиске треков исполнителя: {e}')
        await cb.answer('Произошла ошибка')
