# Используем официальный образ Python 3.12
FROM python:3.12

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем файлы проекта
COPY . .

# Устанавливаем правильные права доступа для всех файлов
RUN chmod -R a+rX .

# Добавляем установку клиента PostgreSQL
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*

# Устанавливаем зависимости через pip (вместо poetry)
RUN pip install --no-cache-dir \
    python-dotenv==1.0.0 \
    django==5.2.3 \
    djangorestframework==3.16.0 \
    gunicorn==23.0.0 \
    aiogram==3.20.0 \
    yandex-music==2.2.0 \
    tenacity==9.1.2 \
    whitenoise==6.9.0 \
    redis==6.2.0 \
    celery==5.5.3 \
    loguru==0.7.3 \
    psycopg2-binary==2.9.10 \
    asyncpg

# Команда по умолчанию (будет переопределена в docker-compose)
CMD ["python", "manage.py", "runserver"]
