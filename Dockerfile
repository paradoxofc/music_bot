FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client make \
    && rm -rf /var/lib/apt/lists/*

# Зависимости ставим одним источником правды — из pyproject/poetry,
# иначе список в Dockerfile расходится с pyproject и версии разъезжаются.
COPY pyproject.toml poetry.lock* ./
RUN pip install --no-cache-dir poetry==1.8.3 \
    && poetry config virtualenvs.create false \
    && poetry install --no-root --only main --no-interaction --no-ansi

COPY . .

RUN chmod +x /app/wait-for-db.sh

CMD ["make", "run.bot"]
