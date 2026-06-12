#!/usr/bin/env python3
"""Импорт chat_id из текстового файла в таблицу users.

Формат файла: один Telegram user id на строку (как search_muzyka_bot_active.txt).

Запуск из корня проекта:
  python3 scripts/import_legacy_users.py
  python3 scripts/import_legacy_users.py --dry-run

В Docker (prod):
  docker compose -f docker-compose.prod.yml exec bot \\
    python3 scripts/import_legacy_users.py
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / 'search_muzyka_bot_active.txt'
SOURCE = 'legacy_import'
BATCH_SIZE = 500


def parse_ids(path: Path) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if not line.isdigit():
            print(f'Пропуск нечисловой строки: {raw!r}', file=sys.stderr)
            continue
        chat_id = int(line)
        if chat_id in seen:
            continue
        seen.add(chat_id)
        ids.append(chat_id)
    return ids


async def ensure_users_table(conn: asyncpg.Connection) -> None:
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
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS is_premium BOOLEAN'
    )
    await conn.execute(
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS downloads_count INTEGER NOT NULL DEFAULT 0'
    )


async def import_ids(ids: list[int], *, dry_run: bool) -> None:
    conn = await asyncpg.connect(
        database=os.environ['POSTGRES_DB'],
        user=os.environ['POSTGRES_USER'],
        password=os.environ['POSTGRES_PASSWORD'],
        host=os.environ['POSTGRES_HOST'],
        port=int(os.environ.get('POSTGRES_PORT', '5432')),
    )
    try:
        await ensure_users_table(conn)
        before = await conn.fetchval('SELECT COUNT(*) FROM users')
        inserted = 0

        if dry_run:
            existing = await conn.fetch(
                'SELECT chat_id FROM users WHERE chat_id = ANY($1::bigint[])',
                ids,
            )
            existing_set = {row['chat_id'] for row in existing}
            would_insert = sum(1 for uid in ids if uid not in existing_set)
            print(f'Файл: {len(ids)} уникальных id')
            print(f'Уже в БД: {len(existing_set)}')
            print(f'Будет добавлено: {would_insert}')
            return

        insert_sql = """
            WITH ins AS (
                INSERT INTO users (chat_id, is_active, source)
                SELECT unnest($1::bigint[]), true, $2
                ON CONFLICT (chat_id) DO NOTHING
                RETURNING chat_id
            )
            SELECT COUNT(*)::int FROM ins
        """
        for i in range(0, len(ids), BATCH_SIZE):
            batch = ids[i : i + BATCH_SIZE]
            inserted += await conn.fetchval(insert_sql, batch, SOURCE) or 0

        after = await conn.fetchval('SELECT COUNT(*) FROM users')
        print(f'Файл: {len(ids)} уникальных id')
        print(f'Добавлено новых строк: {inserted}')
        print(f'Пользователей в БД: {before} → {after} (+{after - before})')
    finally:
        await conn.close()


def main() -> None:
    load_dotenv(ROOT / '.env')

    parser = argparse.ArgumentParser(description='Импорт Telegram chat_id в users')
    parser.add_argument(
        'input',
        nargs='?',
        type=Path,
        default=DEFAULT_INPUT,
        help=f'Путь к файлу (по умолчанию {DEFAULT_INPUT.name})',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Только подсчёт, без записи в БД',
    )
    args = parser.parse_args()

    if not args.input.is_file():
        print(f'Файл не найден: {args.input}', file=sys.stderr)
        sys.exit(1)

    required = ('POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_HOST')
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        print(f'Не заданы переменные окружения: {", ".join(missing)}', file=sys.stderr)
        sys.exit(1)

    ids = parse_ids(args.input)
    if not ids:
        print('В файле нет валидных id', file=sys.stderr)
        sys.exit(1)

    asyncio.run(import_ids(ids, dry_run=args.dry_run))


if __name__ == '__main__':
    main()
