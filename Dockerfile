# syntax=docker/dockerfile:1.6

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DB_HOST=db \
    DB_PORT=5432 \
    DB_USER=postgres \
    DB_PASS=postgres \
    DB_NAME=aiddiag \
    JWT_ISSUER=http://localhost:8000 \
    JWT_AUDIENCE=aiddiag-api \
    JWT_PRIVATE_KEY_PATH=app/static/private.pem \
    JWT_PUBLIC_JWKS_PATH=app/static/jwks.json

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
