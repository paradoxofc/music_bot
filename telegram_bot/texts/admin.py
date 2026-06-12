STATS_MAIN_TEXT = """
📊 <b>Статистика</b>

👥 <b>Всего пользователей:</b> {total_users}
✅ <b>Активных:</b> {active_users}
❌ <b>Заблокировали бота:</b> {blocked_users}

{metrics}
"""


def format_event_stats_block(name: str, stats: dict, total: int | None = None) -> str:
    total_suffix = f' — всего: {total}' if total is not None else ''
    return (
        f'<b>{name}</b>{total_suffix}\n'
        f'• Сегодня: {stats["today"]["count"]} ({stats["today"]["diff_formatted"]})\n'
        f'• Вчера: {stats["yesterday"]["count"]}\n'
        f'• 7 дней: {stats["last_7_days"]["count"]} ({stats["last_7_days"]["diff_formatted"]})\n'
        f'• 30 дней: {stats["last_30_days"]["count"]} ({stats["last_30_days"]["diff_formatted"]})'
    )

REPORT_READY_TEXT = """
📋 <b>Отчёт пользователей</b>

В базе: <b>{users_count}</b> пользователей.
Всего скачано треков: <b>{downloads_total}</b>.
"""

REPORT_EMPTY_TEXT = 'В базе пока нет пользователей'

ADMIN_MAIN_TEXT = """
<b>👋 Привет, {name}!</b>

Добро пожаловать в <b>админ-панель</b> бота.

<i>Выбери раздел ниже:</i>
"""

BROADCASTS_MAIN_TEXT = """
<b>📢 Рассылки</b>

Всего создано: <b>{total}</b>
Запущено: <b>{sent}</b>

<i>Выбери действие:</i>
"""

GET_FILE_INFO_TEXT = """
<b>ℹ️ Получение информации о файле</b>

Отправь файл, а я верну ID и тип.
"""

FILE_INFO_RESULT_TEXT = """
<b>Готово!</b>

<b>Тип файла</b>: {file_type}
<b>ID файла</b>: <code>{file_id}</code>
"""

FILE_INFO_ERROR_TEXT = """
<b>❌ Ошибка</b>

Отправь <b>видео</b>, <b>фото</b> или <b>GIF</b>.
"""

BROADCAST_RETRIEVE_TEXT = """
📣 <b>Рассылка #{id}</b>

📝 <b>Название:</b> {name}
🏷️ <b>Статус:</b> {status}
📎 <b>Вложение:</b> {media}

💬 <b>Текст:</b>
<blockquote>
{text}
</blockquote>

🔘 <b>Кнопки:</b>
{buttons}

<i>Выбери действие:</i>
"""

EDIT_BROADCAST_ENTER_NAME = """
📝 <b>Изменить название</b>

Отправьте новое название рассылки.
"""

EDIT_BROADCAST_ENTER_TEXT = """
💬 <b>Изменить текст</b>

Отправьте новый текст рассылки. Поддерживается HTML форматирование.
"""

EDIT_BROADCAST_ENTER_BUTTONS = """
🔘 <b>Изменить кнопки</b>

Отправьте список кнопок, по одной на строку в формате:
<code>Текст — https://t.me/dev_myz</code>

Чтобы удалить все кнопки, отправьте «нет».
"""

OP_MAIN_TEXT = """
<b>📌 Обязательная подписка (ОП)</b>

Управление проверкой подписки на каналы перед использованием бота.

<i>Выбери действие:</i>
"""

OP_RETRIEVE_TEXT = """
📌 <b>ОП #{id}</b>

📝 <b>Название:</b> {name}
🏷️ <b>Статус:</b> {status}

💬 <b>Текст для пользователя:</b>
<blockquote>
{text}
</blockquote>

📢 <b>Каналы:</b>
{channels}

<i>Бот должен быть администратором в каждом канале, иначе проверка не сработает.</i>

<i>Выбери действие:</i>
"""


def get_op_retrieve_text(op_setup: dict) -> str:
    channels = op_setup.get('channels') or []
    if channels:
        channels_str = '\n'.join(
            f"• <b>{ch['button_text']}</b> — <code>{ch['channel_ref']}</code>"
            for ch in channels
        )
    else:
        channels_str = 'Каналы не добавлены'

    status = 'Включена' if op_setup.get('is_active') else 'Выключена'
    message = (op_setup.get('message') or '').strip() or '—'

    return OP_RETRIEVE_TEXT.format(
        id=op_setup['id'],
        name=op_setup['name'],
        status=status,
        text=message,
        channels=channels_str,
    )


def get_broadcast_retrieve_text(broadcast: dict) -> str:
    if broadcast.get('buttons'):
        buttons_str = "\n".join(
            f"• <b>{btn['text']}</b> — {btn['url']}"
            for btn in broadcast["buttons"]
        )
    else:
        buttons_str = 'Нет кнопок'

    file_type_to_str = {
        'sendMessage': 'Без вложения',
        'sendPhoto': 'Фото',
        'sendAnimation': 'GIF',
        'sendVideo': 'Видео',
    }

    return BROADCAST_RETRIEVE_TEXT.format(
        id=broadcast['id'],
        name=broadcast['name'],
        text=broadcast['message'],
        buttons=buttons_str,
        status='Запущена' if broadcast['is_sent'] else 'Не запущена',
        media=file_type_to_str[broadcast['file_type']]
    )
