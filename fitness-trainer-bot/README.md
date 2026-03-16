# Фитнес-бот с AI-тренером

Telegram-бот с голосовым AI-тренером, тарифами и оплатой через Robokassa.

## Возможности

- **Регистрация** — имя, фамилия, возраст (`/register`, `/edit`).
- **AI-тренер** — ответы на вопросы по тренировкам, питанию, восстановлению (Groq / OpenRouter / Gemini).
- **Тарифы:**
  - **Пробный** — только для зарегистрированных: 2 коротких вопроса бесплатно.
  - **10 вопросов** — 100 ₽ (оплата `/pay 2`).
  - **Чат на месяц** — 1000 ₽, безлимит 30 дней (`/pay 3`).
- **Оплата** — Robokassa (ссылка из бота, ResultURL/SuccessURL в API).

## Команды бота

| Команда | Описание |
|--------|----------|
| `/start` | Приветствие и краткая инструкция |
| `/help` | Список команд |
| `/register` | Регистрация (имя, фамилия, возраст) |
| `/edit` | Изменить свои данные |
| `/tariffs` | Список тарифов |
| `/mytariff` | Текущий тариф и остаток вопросов |
| `/pay 2` | Оплатить тариф «10 вопросов» (100 ₽) |
| `/pay 3` | Оплатить тариф «Чат на месяц» (1000 ₽) |
| `/trainer` | Диалог с AI-тренером (выход — `/cancel`) |
| `/cancel` | Выйти из диалога с тренером или отменить регистрацию |

В интерфейсе есть кнопки: **Тарифы**, **Мой тариф**, **Чат с тренером**.

## Структура проекта

```
fitness-trainer-bot/
├── bot/                 # Telegram-бот
│   ├── handlers/        # Обработчики команд и диалогов
│   ├── services/       # fitness_ai — запросы к AI (Groq, OpenRouter, Gemini)
│   ├── .env             # BOT_TOKEN, API_BASE_URL, OPENROUTER_API_KEY и др.
│   └── main.py
├── api/                 # Backend: платёжный API для Robokassa
│   ├── .env             # ROBOKASSA_*, опционально SQLITE_PATH
│   └── main.py          # /payment/create, /payment/result, /payment/success, /payment/fail
├── db/
│   ├── session.py       # SQLite, users, payments, user_subscriptions
│   └── app.sqlite3      # База (создаётся при первом запуске)
├── requirements.txt   # Зависимости Python (используется и локально, и в Docker)
├── docker-compose.yml
├── Dockerfile
└── README.md
```

## Запуск локально

### 1. Окружение

```bash
cd fitness-trainer-bot
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows
# source .venv/bin/activate   # Linux/macOS

pip install -r requirements.txt
```

Все зависимости перечислены в `requirements.txt`; в Docker они ставятся из этого же файла при сборке образа.

### 2. Переменные окружения

**bot/.env:**

```env
BOT_TOKEN=токен_от_BotFather
API_BASE_URL=http://localhost:8000
OPENROUTER_API_KEY=ключ_с_openrouter.ai
```

**api/.env** (для оплаты):

```env
ROBOKASSA_MERCHANT_LOGIN=...
ROBOKASSA_PASSWORD1=...
ROBOKASSA_PASSWORD2=...
ROBOKASSA_IS_TEST=1
```

Для AI-тренера достаточно одного ключа: `OPENROUTER_API_KEY`, или `GROQ_API_KEY`, или `GEMINI_API_KEY` (см. bot/.env.example).

### 3. Запуск

Терминал 1 — API:

```bash
python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Терминал 2 — бот:

```bash
python -m bot.main
```

## Запуск в Docker (хост/VPS)

Зависимости устанавливаются из `requirements.txt` при сборке образа.

```bash
cd fitness-trainer-bot
# Создать bot/.env и api/.env
docker compose up -d --build
```

Бот и API работают в контейнерах, БД в volume `sqlite_data`. Для приёма платежей укажите в личном кабинете Robokassa Result URL и Success URL на ваш домен (например `https://your-domain.com/payment/result`).

## Просмотр данных в БД на хосте

SQLite, файл по умолчанию: `db/app.sqlite3` (или путь из `SQLITE_PATH`).

По SSH:

```bash
cd /path/to/fitness-trainer-bot
sqlite3 db/app.sqlite3
```

В консоли sqlite3:

```sql
.tables
SELECT * FROM users;
SELECT * FROM user_subscriptions;
SELECT * FROM payments;
.quit
```

В Docker:

```bash
docker exec -it <контейнер_бота_или_api> sqlite3 /app/db/app.sqlite3 "SELECT * FROM users;"
```

## Лицензия

Проект для учебных/личных целей.
