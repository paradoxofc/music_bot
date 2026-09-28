from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from contextlib import suppress
from loguru import logger

from ..constants import EventType
from ..db import send_event
from ..keyboards import get_search_kb
from ..middlewares import YAMServiceMiddleware
from ..services import YAMService
from ..utils import get_error_kb, remember_query, resolve_query

router = Router()
router.message.middleware(YAMServiceMiddleware())
router.callback_query.middleware(YAMServiceMiddleware())

NOT_FOUND_TEXT = '😔 Ничего не найдено. Попробуйте изменить запрос.'
MAX_QUERY_LENGTH = 200


class SearchState(StatesGroup):
    waiting_for_query = State()


@router.message(Command('search'))
async def search_command(msg: types.Message, state: FSMContext) -> None:
    """Обработчик команды /search."""
    await state.set_state(SearchState.waiting_for_query)
    await msg.answer('Введите название песни или исполнителя:')


@router.message(SearchState.waiting_for_query, F.text)
async def search_query(msg: types.Message, state: FSMContext, yam_service: YAMService) -> None:
    """Поиск треков по запросу (после команды /search)."""
    await state.clear()
    await _do_search(msg, (msg.text or '').strip(), yam_service)


# ~F.text.startswith('/') — чтобы неизвестные команды не уходили в поиск.
@router.message(F.text, ~F.text.startswith('/'))
async def search_free_text(msg: types.Message, yam_service: YAMService) -> None:
    """Поиск треков по любому текстовому сообщению."""
    await _do_search(msg, (msg.text or '').strip(), yam_service)


async def _do_search(msg: types.Message, query: str, yam_service: YAMService) -> None:
    """Общая логика поиска."""
    if not query:
        await msg.answer('Пожалуйста, введите текст для поиска.')
        return

    query = query[:MAX_QUERY_LENGTH]
    logger.info(f'Пользователь {msg.from_user.id} ищет: {query!r}')
    await send_event(event_type=EventType.SEARCH, chat_id=msg.from_user.id)

    searching_msg = await msg.answer('🔍 Ищу...')

    try:
        results = await yam_service.search(query)
    except Exception as e:
        logger.exception(f'Ошибка при поиске: {e}')
        await _safe_delete(searching_msg)
        await msg.answer(
            '❌ Произошла ошибка при поиске. Попробуйте позже.',
            reply_markup=get_error_kb(e, context=f'Поисковый запрос: {query}'),
        )
        return

    await _safe_delete(searching_msg)

    if not results or (not results.get('tracks') and not results.get('albums')):
        await msg.answer(NOT_FOUND_TEXT)
        return


    token = await remember_query(query)
    kb = get_search_kb(results, query_token=token)

    await msg.answer(
        f'🔍 Результаты поиска по запросу "{query}":',
        reply_markup=kb,
    )


async def _safe_delete(message: types.Message) -> None:
    """Сообщение «Ищу...» могло быть удалено пользователем — это не ошибка."""
    with suppress(TelegramBadRequest):
        await message.delete()


@router.callback_query(F.data.startswith('search:'))
async def search_callback(cb: types.CallbackQuery, yam_service: YAMService) -> None:
    """Обработчик пагинации поиска."""
    try:
        _, token, page_raw = cb.data.split(':', 2)
        page = int(page_raw)
    except ValueError:
        await cb.answer('Некорректные данные кнопки')
        return

    query = await resolve_query(token)
    if not query:
        await cb.answer('Запрос устарел — отправьте его ещё раз', show_alert=True)
        return

    try:
        results = await yam_service.search(query, page)
        if not results or (not results.get('tracks') and not results.get('albums')):
            await cb.answer('Результаты не найдены')
            return


        kb = get_search_kb(results, query_token=token)
        await cb.message.edit_reply_markup(reply_markup=kb)
        await cb.answer()
    except TelegramBadRequest as e:
        if 'message is not modified' in str(e).lower():
            await cb.answer()
            return
        logger.warning(f'Не удалось обновить список поиска: {e}')
        await cb.answer('Произошла ошибка')
    except Exception as e:
        logger.exception(f'Ошибка при пагинации поиска: {e}')
        await cb.answer('Произошла ошибка')
        if cb.message:
            await cb.message.answer(
                '❌ Произошла ошибка при переключении страницы.',
                reply_markup=get_error_kb(e, context=f'Пагинация поиска: {cb.data}'),
            )


@router.callback_query(F.data.startswith('artist_search:'))
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
    except TelegramBadRequest as e:
        if 'message is not modified' in str(e).lower():
            await cb.answer()
            return
        logger.warning(f'Не удалось показать треки исполнителя: {e}')
        await cb.answer('Произошла ошибка')
    except Exception as e:
        logger.exception(f'Ошибка при поиске треков исполнителя: {e}')
        await cb.answer('Произошла ошибка')
        if cb.message:
            await cb.message.answer(
                '❌ Произошла ошибка при поиске треков исполнителя.',
                reply_markup=get_error_kb(e, context=f'Поиск артиста: {cb.data}'),
            )
