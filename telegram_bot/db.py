import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

import asyncpg
from aiogram.types import User
from loguru import logger
import os

from .constants import EventType

# Конфигурация БД из переменных окружения
POSTGRES_DB = os.getenv('POSTGRES_DB', 'mus_db')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'admin')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', '')
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'db')
POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')

if POSTGRES_HOST == 'db':
    import socket
    try:
        socket.gethostbyname('db')
    except socket.gaierror:
        POSTGRES_HOST = '127.0.0.1'

_db_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


async def init_db_pool():
    """Создаёт пул соединений с PostgreSQL (идемпотентно и без гонок)."""
    global _db_pool
    if _db_pool is not None:
        return _db_pool
    async with _pool_lock:
        if _db_pool is not None:
            return _db_pool
        _db_pool = await asyncpg.create_pool(
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            host=POSTGRES_HOST,
            port=int(POSTGRES_PORT),
            min_size=1,
            max_size=10,
            command_timeout=60,
        )
        async with _db_pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL UNIQUE,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language TEXT,
                    source TEXT,
                    is_active BOOLEAN NOT NULL DEFAULT true,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tracks (
                    track_id TEXT PRIMARY KEY,
                    file_id TEXT NOT NULL,
                    artist_id TEXT,
                    artist_name TEXT,
                    track_title TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS favorites (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    track_id TEXT NOT NULL,
                    title TEXT,
                    artist_id TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (chat_id, track_id)
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id SERIAL PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    chat_id BIGINT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS broadcasts (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT 'Новая рассылка',
                    message TEXT NOT NULL DEFAULT '',
                    file_type TEXT NOT NULL DEFAULT 'sendMessage',
                    file_id TEXT,
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
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS op_setups (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT 'Новая ОП',
                    message TEXT NOT NULL DEFAULT '',
                    is_active BOOLEAN NOT NULL DEFAULT false,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS op_channels (
                    id SERIAL PRIMARY KEY,
                    op_setup_id INTEGER NOT NULL REFERENCES op_setups(id) ON DELETE CASCADE,
                    button_text TEXT NOT NULL,
                    channel_ref TEXT NOT NULL,
                    invite_url TEXT,
                    position INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            await _migrate_users_table(conn)
            await _migrate_schema(conn)
        logger.info("Пул соединений с PostgreSQL создан")
    return _db_pool

@asynccontextmanager
async def acquire() -> AsyncIterator[asyncpg.Connection]:
    """Безопасно берёт соединение из пула и всегда возвращает его обратно.

    Использовать так:
        async with acquire() as conn:
            await conn.fetch(...)
    """
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        yield conn


async def get_db():
    """Возвращает соединение из пула.

    Устаревший способ — предпочтительнее ``async with acquire() as conn``,
    потому что он не теряет соединение при отмене задачи.
    """
    pool = await init_db_pool()
    return await pool.acquire()


async def release_db(conn):
    """Возвращает соединение обратно в пул"""
    pool = await init_db_pool()
    await pool.release(conn)


async def close_db_pool() -> None:
    """Закрывает пул при остановке бота."""
    global _db_pool
    if _db_pool is not None:
        await _db_pool.close()
        _db_pool = None
        logger.info('Пул соединений с PostgreSQL закрыт')


async def _migrate_users_table(conn) -> None:
    """Миграции таблицы users."""
    migrations = (
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS is_premium BOOLEAN',
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS downloads_count INTEGER NOT NULL DEFAULT 0',
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW()',
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS last_reminded_at TIMESTAMPTZ',
        'ALTER TABLE users DROP COLUMN IF EXISTS gender',
        'ALTER TABLE users DROP COLUMN IF EXISTS age',
        'ALTER TABLE users DROP COLUMN IF EXISTS country',
        'ALTER TABLE users DROP COLUMN IF EXISTS city',
    )
    for query in migrations:
        await conn.execute(query)
    await conn.execute('UPDATE users SET last_activity_at = created_at WHERE last_activity_at IS NULL')



async def _migrate_schema(conn) -> None:
    """Индексы и одноразовый backfill счётчика скачиваний."""
    index_queries = (
        'CREATE INDEX IF NOT EXISTS idx_events_type_created ON events (event_type, created_at)',
        'CREATE INDEX IF NOT EXISTS idx_events_chat_type ON events (chat_id, event_type)',
        'CREATE INDEX IF NOT EXISTS idx_users_active ON users (is_active) WHERE is_active = true',
        'CREATE INDEX IF NOT EXISTS idx_users_activity ON users (last_activity_at) WHERE is_active = true',
        'CREATE INDEX IF NOT EXISTS idx_favorites_chat_created ON favorites (chat_id, created_at DESC)',
        'CREATE INDEX IF NOT EXISTS idx_users_created ON users (created_at DESC)',
        'CREATE INDEX IF NOT EXISTS idx_events_created ON events (created_at DESC)',
    )
    for query in index_queries:
        await conn.execute(query)

    has_download_events = await conn.fetchval(
        'SELECT EXISTS (SELECT 1 FROM events WHERE event_type = $1 LIMIT 1)',
        str(EventType.DOWNLOAD),
    )
    total_stored_downloads = await conn.fetchval(
        'SELECT COALESCE(SUM(downloads_count), 0)::bigint FROM users',
    )
    if has_download_events and not total_stored_downloads:
        logger.info('Backfill users.downloads_count из events…')
        await conn.execute(
            """
            UPDATE users u
            SET downloads_count = sub.cnt
            FROM (
                SELECT chat_id, COUNT(*)::int AS cnt
                FROM events
                WHERE event_type = $1
                GROUP BY chat_id
            ) sub
            WHERE u.chat_id = sub.chat_id
            """,
            str(EventType.DOWNLOAD),
        )
        logger.info('Backfill users.downloads_count завершён')


# ========== ПОЛЬЗОВАТЕЛИ ==========

async def create_user(user_data: User, source: str | None) -> Optional[Dict]:
    """Создаёт или обновляет пользователя в БД.

    В результат добавляется служебный ключ ``is_new``: True, если строка была
    именно вставлена (``xmax = 0``), а не обновлена. Это позволяет определить
    первую регистрацию одним запросом, без гонки «прочитали — записали».
    """
    async with acquire() as conn:
        is_premium = bool(getattr(user_data, 'is_premium', None) or False)
        result = await conn.fetchrow(
            """
            INSERT INTO users (
                chat_id, username, first_name, last_name, language, source,
                is_active, is_premium, created_at, last_activity_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, true, $7, NOW(), NOW())
            ON CONFLICT (chat_id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                language = EXCLUDED.language,
                is_premium = EXCLUDED.is_premium,
                is_active = true,
                last_activity_at = NOW()
            RETURNING *, (xmax = 0) AS is_new
            """,
            user_data.id,
            user_data.username,
            user_data.first_name,
            user_data.last_name,
            user_data.language_code,
            source,
            is_premium,
        )
        return dict(result) if result else None


async def ensure_user(user_data: User, source: str | None = None) -> bool:
    """
    Гарантирует наличие пользователя в БД.
    Возвращает True, если пользователь зарегистрирован впервые.
    """
    created = await create_user(user_data, source)
    is_new = bool(created and created.get('is_new'))
    if is_new:
        await send_event(event_type=EventType.REGISTRATION, chat_id=user_data.id)
    return is_new

async def get_user(chat_id: int) -> Optional[Dict]:
    """Получает пользователя по chat_id"""
    async with acquire() as conn:
        result = await conn.fetchrow("SELECT * FROM users WHERE chat_id = $1", chat_id)
        return dict(result) if result else None

async def get_users_count() -> int:
    """Число пользователей без загрузки всех строк."""
    async with acquire() as conn:
        total = await conn.fetchval('SELECT COUNT(*)::int FROM users')
        return int(total or 0)


async def get_all_users_for_report() -> List[Dict]:
    """Все пользователи для Excel-отчёта."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                chat_id, username, first_name, last_name, language, source,
                is_active, created_at, is_premium,
                COALESCE(downloads_count, 0)::int AS downloads_count
            FROM users
            ORDER BY created_at DESC
            """
        )
        return [dict(row) for row in rows]


async def get_downloads_total_count() -> int:
    """Общее число скачиваний (из денормализованного счётчика)."""
    async with acquire() as conn:
        total = await conn.fetchval(
            'SELECT COALESCE(SUM(downloads_count), 0)::int FROM users',
        )
        return int(total or 0)


async def set_blocked_status(chat_id: int, is_blocked: bool) -> Optional[Dict]:
    """Блокирует/разблокирует пользователя"""
    async with acquire() as conn:
        result = await conn.fetchrow(
            "UPDATE users SET is_active = $1 WHERE chat_id = $2 RETURNING *",
            not is_blocked, chat_id
        )
        return dict(result) if result else None

async def set_blocked_status_bulk(chat_ids: List[int]) -> None:
    """Помечает пачку пользователей как заблокировавших бота (после рассылки)."""
    if not chat_ids:
        return
    unique_ids = list(set(chat_ids))
    async with acquire() as conn:
        await conn.execute(
            "UPDATE users SET is_active = false WHERE chat_id = ANY($1::bigint[])",
            unique_ids,
        )


async def update_user_activity(chat_id: int) -> None:
    """Обновляет время последней активности пользователя."""
    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE users
            SET last_activity_at = NOW(), is_active = true
            WHERE chat_id = $1
            """,
            chat_id,
        )


async def get_inactive_user_ids(days: int = 3) -> list[int]:
    """Возвращает chat_id активных пользователей, не заходивших >= days дней."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT chat_id
            FROM users
            WHERE is_active = true
              AND last_activity_at <= NOW() - ($1 * INTERVAL '1 day')
              AND (last_reminded_at IS NULL OR last_reminded_at < last_activity_at)
            ORDER BY chat_id
            """,
            int(days),
        )
        return [row['chat_id'] for row in rows]


async def set_reminded_status_bulk(chat_ids: list[int]) -> None:
    """Помечает пользователей как получивших напоминание."""
    if not chat_ids:
        return
    unique_ids = list(set(chat_ids))
    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE users
            SET last_reminded_at = NOW()
            WHERE chat_id = ANY($1::bigint[])
            """,
            unique_ids,
        )




async def iter_active_user_ids(batch_size: int = 1000) -> AsyncIterator[int]:
    """Курсор по активным пользователям — не тянет всю базу в память."""
    async with acquire() as conn:
        async with conn.transaction():
            cursor = conn.cursor(
                'SELECT chat_id FROM users WHERE is_active = true ORDER BY chat_id'
            )
            async for record in cursor:
                yield record['chat_id']


async def get_active_users_count() -> int:
    """Число активных пользователей (для прогресса рассылки)."""
    async with acquire() as conn:
        total = await conn.fetchval('SELECT COUNT(*)::int FROM users WHERE is_active = true')
        return int(total or 0)


async def try_start_broadcast(broadcast_id: int | str) -> bool:
    """Атомарно помечает рассылку запущенной.

    Возвращает False, если она уже была запущена — защита от двойного клика
    по «Запустить».
    """
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE broadcasts
            SET is_sent = true, updated_at = NOW()
            WHERE id = $1 AND is_sent = false
            RETURNING id
            """,
            int(broadcast_id),
        )
        return row is not None


# ========== ТРЕКИ (КЭШ) ==========

async def save_track(track_id: str, file_id: str, artist_id: str, artist_name: str, track_title: str) -> Optional[Dict]:
    """Сохраняет трек в кэш"""
    async with acquire() as conn:
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

async def delete_track(track_id: str) -> None:
    """Удаляет трек из кэша (например, если file_id протух)."""
    async with acquire() as conn:
        await conn.execute("DELETE FROM tracks WHERE track_id = $1", track_id)


async def get_track(track_id: str) -> Optional[Dict]:
    """Получает трек из кэша"""
    async with acquire() as conn:
        result = await conn.fetchrow("SELECT * FROM tracks WHERE track_id = $1", track_id)
        return dict(result) if result else None


async def get_tracks_by_ids(track_ids: list[str]) -> list[Dict]:
    """Получает несколько треков из кэша одним запросом."""
    if not track_ids:
        return []
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM tracks WHERE track_id = ANY($1::text[])",
            track_ids,
        )
        return [dict(row) for row in rows]

# ========== ИЗБРАННОЕ ==========

async def add_to_favorites(chat_id: int, track_id: str, title: str, artist_id: int | str) -> Optional[Dict]:
    """Добавляет трек в избранное"""
    async with acquire() as conn:
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

async def delete_from_favorites(chat_id: int, track_id: str) -> Optional[Dict]:
    """Удаляет трек из избранного"""
    async with acquire() as conn:
        result = await conn.fetchrow(
            "DELETE FROM favorites WHERE chat_id = $1 AND track_id = $2 RETURNING *",
            chat_id, track_id
        )
        return dict(result) if result else None

async def get_favorites(chat_id: int, page: str | None = None, limit: int = 10) -> Dict[str, Any]:
    """Получает избранное пользователя с пагинацией."""
    async with acquire() as conn:
        page_num = int(page) if page and page.isdigit() else 1
        page_num = max(1, page_num)
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
        total = await conn.fetchval(
            "SELECT COUNT(*)::int FROM favorites WHERE chat_id = $1",
            chat_id,
        )
        total = int(total or 0)
        has_prev = page_num > 1
        has_next = offset + len(rows) < total

        return {
            'results': [dict(row) for row in rows],
            'previous': [str(page_num - 1)] if has_prev else None,
            'next': [str(page_num + 1)] if has_next else None,
        }

async def check_favorite(chat_id: int, track_id: str) -> bool:
    """Проверяет, есть ли трек в избранном"""
    async with acquire() as conn:
        result = await conn.fetchval(
            "SELECT 1 FROM favorites WHERE chat_id = $1 AND track_id = $2 LIMIT 1",
            chat_id, track_id
        )
        return result is not None

# ========== СОБЫТИЯ ==========

async def send_event(event_type: int | str, chat_id: int) -> Optional[Dict]:
    """Логирует событие пользователя"""
    async with acquire() as conn:
        normalized_event_type = str(event_type)
        async with conn.transaction():
            result = await conn.fetchrow(
                """
                INSERT INTO events (event_type, chat_id, created_at)
                VALUES ($1, $2, NOW())
                RETURNING *
                """,
                normalized_event_type,
                chat_id,
            )
            if normalized_event_type == str(EventType.DOWNLOAD):
                await conn.execute(
                    """
                    UPDATE users
                    SET downloads_count = downloads_count + 1
                    WHERE chat_id = $1
                    """,
                    chat_id,
                )
        return dict(result) if result else None


async def get_users_stats() -> Dict[str, int]:
    """Возвращает агрегированную статистику пользователей."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*)::int AS total,
                COUNT(*) FILTER (WHERE is_active = true)::int AS active,
                COUNT(*) FILTER (WHERE is_active = false)::int AS blocked
            FROM users
            """
        )
        if not row:
            return {'total': 0, 'active': 0, 'blocked': 0}
        return {'total': row['total'], 'active': row['active'], 'blocked': row['blocked']}


def _format_period_stats(row) -> Dict[str, Dict[str, int | str] | int]:
    def fmt_diff(current: int, previous: int) -> str:
        return f'{current - previous:+d}'

    if not row:
        return {
            'total': 0,
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
        'total': row['total'],
        'today': {'count': today, 'diff_formatted': fmt_diff(today, yesterday)},
        'yesterday': {'count': yesterday, 'diff_formatted': '+0'},
        'last_7_days': {'count': last_7_days, 'diff_formatted': fmt_diff(last_7_days, prev_7_days)},
        'last_30_days': {'count': last_30_days, 'diff_formatted': fmt_diff(last_30_days, prev_30_days)},
    }


_PERIOD_STATS_SQL = """
    SELECT
        COUNT(*)::int AS total,
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
    FROM {table}
    {where_clause}
"""


async def get_registration_stats() -> Dict[str, Dict[str, int | str] | int]:
    """Возвращает статистику регистраций по периодам."""
    async with acquire() as conn:
        query = _PERIOD_STATS_SQL.format(table='users', where_clause='')
        row = await conn.fetchrow(query)
        return _format_period_stats(row)


async def get_event_type_stats(event_type: int | str) -> Dict[str, Dict[str, int | str] | int]:
    """Возвращает статистику событий по типу и периодам."""
    async with acquire() as conn:
        query = _PERIOD_STATS_SQL.format(
            table='events',
            where_clause='WHERE event_type = $1',
        )
        row = await conn.fetchrow(query, str(event_type))
        return _format_period_stats(row)


# ========== РАССЫЛКИ ==========

async def create_broadcast(name: str = 'Новая рассылка') -> Optional[Dict]:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO broadcasts (name, message, file_type, file_id, is_sent, created_at, updated_at)
            VALUES ($1, '', 'sendMessage', NULL, false, NOW(), NOW())
            RETURNING *
            """,
            name
        )
        return dict(row) if row else None


async def get_broadcast(broadcast_id: int | str) -> Optional[Dict]:
    async with acquire() as conn:
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


async def get_sent_broadcasts_count() -> int:
    """Число рассылок, которые были запущены (is_sent = true)."""
    async with acquire() as conn:
        total = await conn.fetchval(
            'SELECT COUNT(*)::int FROM broadcasts WHERE is_sent = true',
        )
        return int(total or 0)


async def get_broadcasts_summary() -> Dict[str, int]:
    """Сводка по рассылкам: всего создано и сколько запущено."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*)::int AS total,
                COUNT(*) FILTER (WHERE is_sent = true)::int AS sent
            FROM broadcasts
            """
        )
        if not row:
            return {'total': 0, 'sent': 0}
        return {'total': row['total'], 'sent': row['sent']}


async def list_broadcasts(page: int = 1, limit: int = 10) -> Dict[str, Any]:
    async with acquire() as conn:
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


async def update_broadcast(broadcast_id: int | str, data: Dict[str, Any]) -> Optional[Dict]:
    async with acquire() as conn:
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


async def set_broadcast_buttons(broadcast_id: int | str, buttons: List[Dict[str, str]]) -> None:
    async with acquire() as conn:
        bid = int(broadcast_id)
        async with conn.transaction():
            await conn.execute("DELETE FROM broadcast_buttons WHERE broadcast_id = $1", bid)
            if buttons:
                await conn.executemany(
                    """
                    INSERT INTO broadcast_buttons (broadcast_id, text, url, position)
                    VALUES ($1, $2, $3, $4)
                    """,
                    [(bid, b['text'], b['url'], pos) for pos, b in enumerate(buttons)],
                )


# ========== ОБЯЗАТЕЛЬНАЯ ПОДПИСКА (ОП) ==========

async def create_op_setup(name: str = 'Новая ОП') -> Optional[Dict]:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO op_setups (name, message, is_active, created_at, updated_at)
            VALUES ($1, '', false, NOW(), NOW())
            RETURNING *
            """,
            name,
        )
        return dict(row) if row else None


async def get_op_setup(op_setup_id: int | str) -> Optional[Dict]:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM op_setups WHERE id = $1", int(op_setup_id))
        if not row:
            return None
        data = dict(row)
        channel_rows = await conn.fetch(
            """
            SELECT button_text, channel_ref, invite_url
            FROM op_channels
            WHERE op_setup_id = $1
            ORDER BY position ASC, id ASC
            """,
            int(op_setup_id),
        )
        data['channels'] = [dict(r) for r in channel_rows]
        return data


async def list_op_setups(page: int = 1, limit: int = 10) -> Dict[str, Any]:
    async with acquire() as conn:
        safe_page = max(1, int(page))
        offset = (safe_page - 1) * limit
        rows = await conn.fetch(
            """
            SELECT id, name, is_active, created_at
            FROM op_setups
            ORDER BY id DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )
        total = await conn.fetchval("SELECT COUNT(*)::int FROM op_setups")
        has_prev = safe_page > 1
        has_next = (offset + len(rows)) < int(total or 0)
        return {
            'results': [dict(r) for r in rows],
            'previous_page': safe_page - 1 if has_prev else None,
            'next_page': safe_page + 1 if has_next else None,
            'page': safe_page,
        }


async def update_op_setup(op_setup_id: int | str, data: Dict[str, Any]) -> Optional[Dict]:
    async with acquire() as conn:
        fields = []
        values = []
        idx = 1
        for key in ('name', 'message', 'is_active'):
            if key in data:
                fields.append(f"{key} = ${idx}")
                values.append(data[key])
                idx += 1

        if not fields:
            return await get_op_setup(op_setup_id)

        fields.append("updated_at = NOW()")
        values.append(int(op_setup_id))
        query = f"UPDATE op_setups SET {', '.join(fields)} WHERE id = ${idx} RETURNING *"
        row = await conn.fetchrow(query, *values)
        return dict(row) if row else None


async def set_op_channels(op_setup_id: int | str, channels: List[Dict[str, str]]) -> None:
    async with acquire() as conn:
        oid = int(op_setup_id)
        async with conn.transaction():
            await conn.execute("DELETE FROM op_channels WHERE op_setup_id = $1", oid)
            if channels:
                await conn.executemany(
                    """
                    INSERT INTO op_channels (op_setup_id, button_text, channel_ref, invite_url, position)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    [
                        (
                            oid,
                            channel['button_text'],
                            channel['channel_ref'],
                            channel.get('invite_url'),
                            pos,
                        )
                        for pos, channel in enumerate(channels)
                    ],
                )


async def activate_op_setup(op_setup_id: int | str) -> Optional[Dict]:
    async with acquire() as conn:
        oid = int(op_setup_id)
        async with conn.transaction():
            await conn.execute(
                "UPDATE op_setups SET is_active = false, updated_at = NOW() WHERE is_active = true"
            )
            row = await conn.fetchrow(
                """
                UPDATE op_setups SET is_active = true, updated_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                oid,
            )
        return dict(row) if row else None


async def deactivate_op_setup(op_setup_id: int | str) -> Optional[Dict]:
    return await update_op_setup(op_setup_id, {'is_active': False})


async def get_active_op_setup() -> Optional[Dict]:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM op_setups
            WHERE is_active = true
            ORDER BY id DESC
            LIMIT 1
            """
        )
        if not row:
            return None
        data = dict(row)
        channel_rows = await conn.fetch(
            """
            SELECT button_text, channel_ref, invite_url
            FROM op_channels
            WHERE op_setup_id = $1
            ORDER BY position ASC, id ASC
            """,
            data['id'],
        )
        data['channels'] = [dict(r) for r in channel_rows]
        return data
