from aiogram import Dispatcher
from .handlers import main, search, download, common, favorites, admin, op
from .handlers import inline_mode as inline


def setup_routers(dp: Dispatcher):
    """Регистрирует роутеры."""
    dp.include_router(inline.router)  # Inline-режим должен быть первым
    dp.include_router(admin.router)
    dp.include_router(op.router)
    dp.include_router(common.router)
    dp.include_router(main.router)
    dp.include_router(search.router)
    dp.include_router(download.router)
    dp.include_router(favorites.router)
