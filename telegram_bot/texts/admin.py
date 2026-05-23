STATS_MAIN_TEXT = """
📊 <b>Статистика</b>

👥 <b>Всего пользователей:</b> {total_users}
✅ <b>Активных:</b> {active_users}

<b>Выберите тип события</b>, по которому хотите получить статистику:
"""

STATS_EVENT_TYPE_TEXT = """
📊 <b>{event_name}</b>

📅 <b>Сегодня:</b> {today}
📅 <b>Вчера:</b> {yesterday}
🗓 <b>За 7 дней:</b> {last_7_days}
🗓 <b>За 30 дней:</b> {last_30_days}
"""

ADMIN_MAIN_TEXT = """
<b>👋 Привет, {name}!</b>

Добро пожаловать в <b>админ-панель</b> бота.

<i>Выбери раздел ниже:</i>
"""

BROADCASTS_MAIN_TEXT = """
<b>📢 Рассылки</b>

Здесь можно управлять рассылками.

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
<code>Текст — https://example.com</code>

Чтобы удалить все кнопки, отправьте «нет».
"""

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
