FROM python:3.12

WORKDIR /app

COPY . .

RUN chmod -R a+rX . && chmod +x /app/wait-for-db.sh

RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    python-dotenv==1.0.0 \
    aiogram==3.20.0 \
    yandex-music[async]==3.0.0 \
    tenacity==9.1.2 \
    redis==6.2.0 \
    loguru==0.7.3 \
    asyncpg==0.30.0 \
    aiohttp==3.11.0 \
    openpyxl==3.1.5

CMD ["make", "run.bot"]
