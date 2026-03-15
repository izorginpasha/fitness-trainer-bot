# Архитектура: фитнес-бот с платёжной системой Robokassa

## Общая схема

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Telegram  │────▶│     BOT     │────▶│     API     │
│    User     │◀────│  (Telegram  │◀────│  (backend)  │
└─────────────┘     │   client)   │     └──────┬──────┘
                    └──────┬──────┘            │
                           │                   │
                           │            ┌──────▼──────┐
                           │            │     DB      │
                           │            │  (данные)   │
                           │            └──────┬──────┘
                           │                   │
                    ┌──────▼──────┐            │
                    │  Robokassa  │◀───────────┘
                    │  (оплата)   │   ResultURL, SuccessURL
                    └─────────────┘
```

---

## 1. Структура проекта

```
fitness-trainer-bot/
├── bot/                    # Telegram-бот
│   ├── handlers/           # Обработчики команд и сцен
│   ├── keyboards/          # Клавиатуры
│   ├── services/           # Логика (подписки, платежи)
│   └── main.py
├── api/                    # Backend API
│   ├── routes/             # Эндпоинты (платежи, вебхуки)
│   ├── services/           # Robokassa, подписки
│   ├── models/             # Pydantic/SQLAlchemy схемы
│   └── main.py
├── db/                     # База данных
│   ├── models/             # Сущности (User, Payment, Subscription)
│   ├── migrations/         # Миграции
│   └── session.py          # Подключение к БД
└── ARCHITECTURE.md
```

---

## 2. База данных (db)

### Основные сущности

| Таблица       | Назначение |
|---------------|------------|
| **users**     | `telegram_id`, `username`, `created_at`, `is_active` |
| **subscriptions** | Тарифы: название, цена, срок (день/месяц/год) |
| **payments**  | Платежи: `user_id`, `subscription_id`, `out_sum`, `inv_id`, `status`, `robokassa_*`, `created_at` |
| **user_subscriptions** | Связь пользователь–подписка: `user_id`, `subscription_id`, `expires_at`, `is_active` |

### Поля платежа (payments)

- `id`, `user_id`, `subscription_id`
- `out_sum` — сумма заказа
- `inv_id` — уникальный номер заказа (для Robokassa)
- `status`: `pending` | `success` | `fail` | `expired`
- `signature` — подпись запроса (для проверки)
- `created_at`, `paid_at`

---

## 3. API (api)

### Роль

- Создание платежа и формирование ссылки/данных для Robokassa.
- Приём уведомлений от Robokassa (ResultURL, SuccessURL, FailURL).
- Проверка подписи и обновление статуса платежа в БД.
- Выдача боту информации о пользователях и подписках (по необходимости).

### Эндпоинты

| Метод | Путь | Назначение |
|-------|------|------------|
| POST | `/payment/create` | Создать платёж: `user_id`, `subscription_id` → вернуть URL оплаты и `inv_id` |
| POST | `/payment/result` | **ResultURL** — уведомление от Robokassa (подпись Пароль №2), обновить статус в БД |
| GET  | `/payment/success` | **SuccessURL** — редирект после успешной оплаты (можно вернуть страницу «Спасибо» или deep link в бота) |
| GET  | `/payment/fail`    | **FailURL** — редирект при отказе/ошибке |

### Логика создания платежа (Robokassa)

1. Создать запись в `payments` со статусом `pending`, сгенерировать уникальный `inv_id`.
2. Посчитать подпись:  
   `MD5(MerchantLogin:OutSum:InvId:Password1[:Shp_*=*...])`.
3. Вернуть боту URL:  
   `https://auth.robokassa.ru/Merchant/Index.aspx?MerchantLogin=...&OutSum=...&InvId=...&SignatureValue=...&Description=...`

### Логика ResultURL (уведомление от Robokassa)

1. Принять POST: `OutSum`, `InvId`, `SignatureValue`, опционально `Shp_*`.
2. Проверить подпись с **Паролем №2**.
3. Найти платёж по `InvId`, обновить `status = success`, `paid_at`.
4. Активировать/продлить подписку в `user_subscriptions`.
5. Ответить Robokassa: `OK<inv_id>`.

---

## 4. Бот (bot)

### Сценарии с оплатой

1. **Выбор тарифа**  
   Пользователь выбирает подписку → бот запрашивает у API создание платежа → получает URL.

2. **Переход на оплату**  
   Бот отправляет кнопку/ссылку «Оплатить» с URL от API (или инлайн-кнопку с URL).

3. **После оплаты**  
   - **SuccessURL**: можно открывать `https://t.me/YourBot?start=pay_success_<inv_id>` — бот по `inv_id` проверит статус в API/БД и напишет «Подписка активирована».
   - **ResultURL**: API уже обновил БД; при следующем сообщении пользователя бот может показать обновлённый статус подписки.
   - Опционально: API при успешном ResultURL отправляет webhook боту или бот периодически опрашивает API по `inv_id` при `start=pay_success_<inv_id>`.

### Сервисы бота

- **PaymentService** — вызов API `POST /payment/create`, сохранение `inv_id` в контексте пользователя (или в БД).
- **SubscriptionService** — проверка активной подписки через API или локальную БД (если бот имеет доступ к БД).

---

## 5. Поток оплаты (последовательность)

```
1. Пользователь в боте нажимает «Купить подписку» → выбирает тариф.
2. Бот → API: POST /payment/create { user_id, subscription_id }.
3. API создаёт запись в payments (pending), считает подпись, возвращает payment_url, inv_id.
4. Бот отправляет пользователю кнопку «Оплатить» (payment_url).
5. Пользователь переходит на Robokassa, оплачивает.
6. Robokassa:
   - отправляет POST на ResultURL → API проверяет подпись, ставит status=success, активирует подписку, отвечает OK<inv_id>;
   - перенаправляет пользователя на SuccessURL (например, t.me/bot?start=pay_<inv_id>).
7. Пользователь возвращается в бота (по кнопке или по ссылке).
8. Бот по start=pay_<inv_id> или по user_id запрашивает статус подписки и пишет «Оплата прошла, подписка активна до …».
```

---

## 6. Безопасность

- **Пароли Robokassa** (Пароль №1 и №2) хранить только в API, в переменных окружения, не отдавать в бота.
- ResultURL проверять только по подписи с Паролем №2; не доверять только `InvId` и сумме.
- Использовать HTTPS для API и для ResultURL/SuccessURL/FailURL.
- В БД хранить только необходимые данные для платежей; не логировать полные номера карт.

---

## 7. Конфигурация (пример .env)

```env
# Bot
BOT_TOKEN=...

# API
API_BASE_URL=https://your-api.com
ROBOKASSA_MERCHANT_LOGIN=...
ROBOKASSA_PASSWORD1=...
ROBOKASSA_PASSWORD2=...
ROBOKASSA_IS_TEST=1

# DB
DATABASE_URL=postgresql://user:pass@localhost/fitness_bot
```

---

## 8. Тестовый режим Robokassa

- В личном кабинете Robokassa включить тестовый режим.
- Использовать тестовые пароли и `IsTest=1` в запросах.
- Проверять сценарии Success, Fail и ResultURL перед продакшеном.

Эта архитектура позволяет разделить бота (Telegram), платёжную логику и подписи (API + Robokassa) и данные (DB) и безопасно проводить оплаты через Robokassa.
