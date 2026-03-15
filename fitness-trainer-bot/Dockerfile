FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY . /app

RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    python-telegram-bot \
    httpx \
    python-dotenv

CMD ["python", "-m", "bot.main"]

