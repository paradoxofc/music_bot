import asyncpg
from loguru import logger
from typing import Optional, List, Dict, Any
from aiogram.types import User
import os

# Конфигурация БД из переменных окружения
POSTGRES_DB = os.getenv('POSTGRES_DB', 'mus_db')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'admin')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', '')
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'db')
POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')

_db_pool = None

async def init_db_pool():
    """Создаёт пул соединений с PostgreSQL"""
    global _db_pool
    if _db_pool is None:
        _db_pool = await asyncpg.create_pool(
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            min_size=1,
            max_size=10
        )
        async with _db_pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS broadcasts (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT 'Новая рассылка',
                    message TEXT NOT NULL DEFAULT '',
                    file_type TEXT NOT NULL DEFAULT 'sendMessage',
                    file_id TEXT NULL,
                    is_sent BOOLEAN NOT NULL DEFAULT false,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS broadcast_buttons (
                    id SERIAL PRIMARY KEY,
                    broadcast_id INTEGER NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
                    text TEXT NOT NULL,
                    url TEXT NOT NULL,
                    position INTEGER NOT NULL DEFAULT 0
                )
                """
            )
        logger.info("Пул соединений с PostgreSQL создан")
    return _db_pool

async def get_db():
    """Возвращает соединение из пула"""
    pool = await init_db_pool()
    return await pool.acquire()

async def release_db(conn):
    """Возвращает соединение обратно в пул"""
    pool = await init_db_pool()
    await pool.release(conn)

# ========== ПОЛЬЗОВАТЕЛИ ==========

async def create_user(user_data: User, source: str | None) -> Optional[Dict]:
    """Создаёт пользователя в БД"""
    conn = await get_db()
    try:
        result = await conn.fetchrow(
            """
            INSERT INTO users (chat_id, username, first_name, last_name, language, source, is_active, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, true, NOW())
            ON CONFLICT (chat_id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                language = EXCLUDED.language
            RETURNING *
            """,
            user_data.id,
            user_data.username,
            user_data.first_name,
            user_data.last_name,
            user_data.language_code,
            source
        )
        return dict(result) if result else None
    finally:
        await release_db(conn)

async def get_user(chat_id: int) -> Optional[Dict]:
    """Получает пользователя по chat_id"""
    conn = await get_db()
    try:
        result = await conn.fetchrow("SELECT * FROM users WHERE chat_id = $1", chat_id)
        return dict(result) if result else None
    finally:
        await release_db(conn)

async def set_blocked_status(chat_id: int, is_blocked: bool) -> Optional[Dict]:
    """Блокирует/разблокирует пользователя"""
    conn = await get_db()
    try:
        result = await conn.fetchrow(
            "UPDATE users SET is_active = $1 WHERE chat_id = $2 RETURNING *",
            not is_blocked, chat_id
        )
        return dict(result) if result else None
    finally:
        await release_db(conn)

# ========== ТРЕКИ (КЭШ) ==========

async def save_track(track_id: str, file_id: str, artist_id: str, artist_name: str, track_title: str) -> Optional[Dict]:
    """Сохраняет трек в кэш"""
    conn = await get_db()
    try:
        result = await conn.fetchrow(
            """
            INSERT INTO tracks (track_id, file_id, artist_id, artist_name, track_title, created_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (track_id) DO UPDATE SET
                file_id = EXCLUDED.file_id,
                artist_name = EXCLUDED.artist_name,
                track_title = EXCLUDED.track_title
            RETURNING *
            """,
            track_id, file_id, artist_id, artist_name, track_title
        )
        return dict(result) if result else None
    finally:
        await release_db(conn)

async def get_track(track_id: str) -> Optional[Dict]:
    """Получает трек из кэша"""
    conn = await get_db()
    try:
        result = await conn.fetchrow("SELECT * FROM tracks WHERE track_id = $1", track_id)
        return dict(result) if result else None
    finally:
        await release_db(conn)

# ========== ИЗБРАННОЕ ==========

async def add_to_favorites(chat_id: int, track_id: str, title: str, artist_id: int | str) -> Optional[Dict]:
    """Добавляет трек в избранное"""
    conn = await get_db()
    try:
        normalized_artist_id = str(artist_id)
        result = await conn.fetchrow(
            """
            INSERT INTO favorites (chat_id, track_id, title, artist_id, created_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (chat_id, track_id) DO NOTHING
            RETURNING *
            """,
            chat_id, track_id, title, normalized_artist_id
        )
        return dict(result) if result else None
    finally:
        await release_db(conn)

async def delete_from_favorites(chat_id: int, track_id: str) -> Optional[Dict]:
    """Удаляет трек из избранного"""
    conn = await get_db()
    try:
        result = await conn.fetchrow(
            "DELETE FROM favorites WHERE chat_id = $1 AND track_id = $2 RETURNING *",
            chat_id, track_id
        )
        return dict(result) if result else None
    finally:
        await release_db(conn)

async def get_favorites(chat_id: int, page: str | None = None, limit: int = 10) -> List[Dict]:
    """Получает избранное пользователя с пагинацией"""
    conn = await get_db()
    try:
        offset = 0
        if page and page.isdigit():
            page_num = int(page)
            offset = (page_num - 1) * limit
        
        rows = await conn.fetch(
            """
            SELECT * FROM favorites 
            WHERE chat_id = $1 
            ORDER BY created_at DESC 
            LIMIT $2 OFFSET $3
            """,
            chat_id, limit, offset
        )
        return [dict(row) for row in rows]
    finally:
        await release_db(conn)

async def check_favorite(chat_id: int, track_id: str) -> bool:
    """Проверяет, есть ли трек в избранном"""
    conn = await get_db()
    try:
        result = await conn.fetchval(
            "SELECT 1 FROM favorites WHERE chat_id = $1 AND track_id = $2 LIMIT 1",
            chat_id, track_id
        )
        return result is not None
    finally:
        await release_db(conn)

# ========== СОБЫТИЯ ==========

async def send_event(event_type: int | str, chat_id: int) -> Optional[Dict]:
    """Логирует событие пользователя"""
    conn = await get_db()
    try:
        normalized_event_type = str(event_type)
        result = await conn.fetchrow(
            "INSERT INTO events (event_type, chat_id, created_at) VALUES ($1, $2, NOW()) RETURNING *",
            normalized_event_type, chat_id
        )
        return dict(result) if result else None
    finally:
        await release_db(conn)


async def get_users_stats() -> Dict[str, int]:
    """Возвращает агрегированную статистику пользователей."""
    conn = await get_db()
    try:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*)::int AS total,
                COUNT(*) FILTER (WHERE is_active = true)::int AS active
            FROM users
            """
        )
        if not row:
            return {'total': 0, 'active': 0}
        return {'total': row['total'], 'active': row['active']}
    finally:
        await release_db(conn)


async def get_event_type_stats(event_type: int | str) -> Dict[str, Dict[str, int | str]]:
    """Возвращает статистику событий по типу и периодам."""
    conn = await get_db()
    try:
        et = str(event_type)
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE)::int AS today,
                COUNT(*) FILTER (
                    WHERE created_at >= CURRENT_DATE - INTERVAL '1 day'
                      AND created_at < CURRENT_DATE
                )::int AS yesterday,
                COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE - INTERVAL '7 day')::int AS last_7_days,
                COUNT(*) FILTER (
                    WHERE created_at >= CURRENT_DATE - INTERVAL '14 day'
                      AND created_at < CURRENT_DATE - INTERVAL '7 day'
                )::int AS prev_7_days,
                COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE - INTERVAL '30 day')::int AS last_30_days,
                COUNT(*) FILTER (
                    WHERE created_at >= CURRENT_DATE - INTERVAL '60 day'
                      AND created_at < CURRENT_DATE - INTERVAL '30 day'
                )::int AS prev_30_days
            FROM events
            WHERE event_type = $1
            """,
            et
        )

        def fmt_diff(current: int, previous: int) -> str:
            diff = current - previous
            return f'{diff:+d}'

        if not row:
            return {
                'today': {'count': 0, 'diff_formatted': '+0'},
                'yesterday': {'count': 0, 'diff_formatted': '+0'},
                'last_7_days': {'count': 0, 'diff_formatted': '+0'},
                'last_30_days': {'count': 0, 'diff_formatted': '+0'},
            }

        today = row['today']
        yesterday = row['yesterday']
        last_7_days = row['last_7_days']
        prev_7_days = row['prev_7_days']
        last_30_days = row['last_30_days']
        prev_30_days = row['prev_30_days']

        return {
            'today': {'count': today, 'diff_formatted': fmt_diff(today, yesterday)},
            'yesterday': {'count': yesterday, 'diff_formatted': '+0'},
            'last_7_days': {'count': last_7_days, 'diff_formatted': fmt_diff(last_7_days, prev_7_days)},
            'last_30_days': {'count': last_30_days, 'diff_formatted': fmt_diff(last_30_days, prev_30_days)},
        }
    finally:
        await release_db(conn)


# ========== РАССЫЛКИ ==========

async def create_broadcast(name: str = 'Новая рассылка') -> Optional[Dict]:
    conn = await get_db()
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO broadcasts (name, message, file_type, file_id, is_sent, created_at, updated_at)
            VALUES ($1, '', 'sendMessage', NULL, false, NOW(), NOW())
            RETURNING *
            """,
            name
        )
        return dict(row) if row else None
    finally:
        await release_db(conn)


async def get_broadcast(broadcast_id: int | str) -> Optional[Dict]:
    conn = await get_db()
    try:
        row = await conn.fetchrow("SELECT * FROM broadcasts WHERE id = $1", int(broadcast_id))
        if not row:
            return None
        data = dict(row)
        buttons_rows = await conn.fetch(
            """
            SELECT text, url
            FROM broadcast_buttons
            WHERE broadcast_id = $1
            ORDER BY position ASC, id ASC
            """,
            int(broadcast_id)
        )
        data['buttons'] = [dict(r) for r in buttons_rows]
        return data
    finally:
        await release_db(conn)


async def list_broadcasts(page: int = 1, limit: int = 10) -> Dict[str, Any]:
    conn = await get_db()
    try:
        safe_page = max(1, int(page))
        offset = (safe_page - 1) * limit
        rows = await conn.fetch(
            """
            SELECT id, name, is_sent, created_at
            FROM broadcasts
            ORDER BY id DESC
            LIMIT $1 OFFSET $2
            """,
            limit, offset
        )
        total = await conn.fetchval("SELECT COUNT(*)::int FROM broadcasts")
        has_prev = safe_page > 1
        has_next = (offset + len(rows)) < int(total or 0)
        return {
            'results': [dict(r) for r in rows],
            'previous_page': safe_page - 1 if has_prev else None,
            'next_page': safe_page + 1 if has_next else None,
            'page': safe_page,
        }
    finally:
        await release_db(conn)


async def update_broadcast(broadcast_id: int | str, data: Dict[str, Any]) -> Optional[Dict]:
    conn = await get_db()
    try:
        fields = []
        values = []
        idx = 1
        for key in ('name', 'message', 'file_type', 'file_id', 'is_sent'):
            if key in data:
                fields.append(f"{key} = ${idx}")
                values.append(data[key])
                idx += 1

        if not fields:
            return await get_broadcast(broadcast_id)

        fields.append("updated_at = NOW()")
        values.append(int(broadcast_id))
        query = f"UPDATE broadcasts SET {', '.join(fields)} WHERE id = ${idx} RETURNING *"
        row = await conn.fetchrow(query, *values)
        return dict(row) if row else None
    finally:
        await release_db(conn)


async def set_broadcast_buttons(broadcast_id: int | str, buttons: List[Dict[str, str]]) -> None:
    conn = await get_db()
    try:
        bid = int(broadcast_id)
        await conn.execute("DELETE FROM broadcast_buttons WHERE broadcast_id = $1", bid)
        for pos, button in enumerate(buttons):
            await conn.execute(
                """
                INSERT INTO broadcast_buttons (broadcast_id, text, url, position)
                VALUES ($1, $2, $3, $4)
                """,
                bid, button['text'], button['url'], pos
            )
    finally:
        await release_db(conn)
