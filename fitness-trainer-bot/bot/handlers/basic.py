import os
import hashlib
from datetime import datetime
import urllib.parse

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

from db.session import upsert_user, get_user_by_telegram_id


MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("/start"), KeyboardButton("/help")],
        [KeyboardButton("/register"), KeyboardButton("/cancel")],
    ],
    resize_keyboard=True,
)


TARIFFS = {
    "1": {
        "code": "basic",
        "name": "Базовый",
        "price": 990.0,
        "description": "Базовый тариф: персональный план тренировок",
    },
    "2": {
        "code": "advanced",
        "name": "Продвинутый",
        "price": 1990.0,
        "description": "Продвинутый тариф: тренировки + поддержка в чате",
    },
    "3": {
        "code": "premium",
        "name": "Премиум",
        "price": 3990.0,
        "description": "Премиум тариф: максимум внимания и индивидуальный подход",
    },
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот.", reply_markup=MAIN_KEYBOARD)


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(update.message.text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Список команд:\n"
        "/start - начать работу с ботом\n"
        "/help - показать это сообщение с командами\n"
        "/register - регистрация (имя, фамилия, возраст)\n"
        "/edit - редактировать сохранённые данные\n"
        "/tariffs - посмотреть доступные тарифы\n"
        "/pay <номер_тарифа> - оплатить тариф (например, /pay 1)\n"
        "/cancel - отменить текущую операцию регистрации/редактирования\n"
    )
    await update.message.reply_text(text, reply_markup=MAIN_KEYBOARD)


# Состояния диалога регистрации
FIRST_NAME, LAST_NAME, AGE = range(3)


async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_user = update.effective_user
    if not tg_user or not tg_user.id:
        await update.message.reply_text(
            "Не удалось получить ваш Telegram ID. Попробуйте написать боту напрямую из личного чата."
        )
        return ConversationHandler.END

    telegram_id = tg_user.id
    existing = get_user_by_telegram_id(telegram_id)

    if existing:
        await update.message.reply_text(
            "Вы уже зарегистрированы:\n"
            f"Имя: {existing.get('first_name') or '-'}\n"
            f"Фамилия: {existing.get('last_name') or '-'}\n"
            f"Возраст: {existing.get('age') or '-'}\n\n"
            "Если хотите изменить данные, отправьте команду /edit.\n"
            "Если всё верно, ничего делать не нужно."
        )
        return ConversationHandler.END

    await update.message.reply_text("Давайте зарегистрируемся.\nВведите ваше имя:")
    return FIRST_NAME


async def edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_user = update.effective_user
    if not tg_user or not tg_user.id:
        await update.message.reply_text(
            "Не удалось получить ваш Telegram ID. Попробуйте написать боту напрямую из личного чата."
        )
        return ConversationHandler.END

    telegram_id = tg_user.id
    existing = get_user_by_telegram_id(telegram_id)

    if not existing:
        await update.message.reply_text(
            "У вас ещё нет сохранённых данных. Сначала пройдите регистрацию командой /register."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Сейчас вы можете отредактировать свои данные.\n"
        f"Текущие значения:\n"
        f"Имя: {existing.get('first_name') or '-'}\n"
        f"Фамилия: {existing.get('last_name') or '-'}\n"
        f"Возраст: {existing.get('age') or '-'}\n\n"
        "Введите новое имя (или отправьте то же самое):"
    )
    return FIRST_NAME


async def register_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["first_name"] = update.message.text.strip()
    await update.message.reply_text("Введите вашу фамилию:")
    return LAST_NAME


async def register_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["last_name"] = update.message.text.strip()
    await update.message.reply_text("Введите ваш возраст (числом):")
    return AGE


async def register_age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    age_text = update.message.text.strip()
    if not age_text.isdigit() or int(age_text) <= 0:
        await update.message.reply_text("Пожалуйста, введите возраст целым положительным числом, например: 25")
        return AGE

    context.user_data["age"] = int(age_text)

    first_name = context.user_data["first_name"]
    last_name = context.user_data["last_name"]
    age = context.user_data["age"]

    tg_user = update.effective_user
    if not tg_user or not tg_user.id:
        await update.message.reply_text(
            "Не удалось получить ваш Telegram ID. Регистрация не может быть завершена. "
            "Попробуйте написать боту напрямую из личного чата, а не из канала или группы."
        )
        return ConversationHandler.END

    telegram_id = tg_user.id
    username = f"@{tg_user.username}" if tg_user.username else None

    db_user_id = upsert_user(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        age=age,
    )

    await update.message.reply_text(
        "Данные сохранены!\n"
        f"Username: {username or '-'}\n"
        f"Имя: {first_name}\n"
        f"Фамилия: {last_name}\n"
        f"Возраст: {age}\n"
    )

    await update.message.reply_text(
        "Операция завершена.\n\n"
        "Теперь вы можете выбрать тариф командой /tariffs\n"
        "и затем оплатить его командой /pay.",
        reply_markup=MAIN_KEYBOARD,
    )

    return ConversationHandler.END


async def tariffs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Доступные тарифы:\n\n"
        "1️⃣ Базовый — 990 ₽ / месяц\n"
        "   • Персональный план тренировок\n"
        "   • 1 корректировка плана в месяц\n\n"
        "2️⃣ Продвинутый — 1 990 ₽ / месяц\n"
        "   • Всё из Базового\n"
        "   • Поддержка в чате 5 дней в неделю\n"
        "   • До 4 корректировок плана в месяц\n\n"
        "3️⃣ Премиум — 3 990 ₽ / месяц\n"
        "   • Всё из Продвинутого\n"
        "   • Еженедельный разбор прогресса\n"
        "   • Индивидуальные рекомендации по питанию\n\n"
        "Чтобы оплатить тариф, используйте команду:\n"
        "/pay 1 — Базовый\n"
        "/pay 2 — Продвинутый\n"
        "/pay 3 — Премиум"
    )
    await update.message.reply_text(text, reply_markup=MAIN_KEYBOARD)


async def pay_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Укажите номер тарифа.\n"
            "Примеры:\n"
            "/pay 1 — Базовый\n"
            "/pay 2 — Продвинутый\n"
            "/pay 3 — Премиум"
        )
        return

    tariff_key = context.args[0].strip()
    tariff = TARIFFS.get(tariff_key)
    if not tariff:
        await update.message.reply_text(
            "Неизвестный тариф. Используйте:\n"
            "/pay 1, /pay 2 или /pay 3."
        )
        return

    api_base_url = os.getenv("API_BASE_URL") or "http://localhost:8000"
    print("DEBUG API_BASE_URL =", repr(api_base_url))

    tg_user = update.effective_user
    if not tg_user or not tg_user.id:
        await update.message.reply_text(
            "Не удалось получить ваш Telegram ID. Попробуйте написать боту напрямую из личного чата."
        )
        return

    import httpx

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{api_base_url.rstrip('/')}/payment/create",
                json={
                    "telegram_id": tg_user.id,
                    "tariff_code": tariff["code"],
                    "out_sum": tariff["price"],
                    "description": tariff["description"],
                },
            )
        if resp.status_code != 200:
            await update.message.reply_text(
                "Не удалось создать платёж. Попробуйте позже или свяжитесь с тренером."
            )
            return

        data = resp.json()
        payment_url = data.get("payment_url")
        inv_id = data.get("inv_id")
    except Exception:
        await update.message.reply_text(
            "Произошла ошибка при обращении к серверу оплаты. Попробуйте позже."
        )
        return

    if not payment_url:
        await update.message.reply_text(
            "Сервер не вернул ссылку на оплату. Попробуйте позже."
        )
        return

    await update.message.reply_text(
        f"Тариф: {tariff['name']} — {int(tariff['price'])} ₽\n\n"
        "Перейдите по ссылке для оплаты через Robokassa:\n"
        f"{payment_url}\n\n"
        f"Номер счёта: {inv_id}"
    )


async def register_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Регистрация отменена.")
    return ConversationHandler.END


def register_handlers(app: Application) -> None:
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("tariffs", tariffs_command))
    app.add_handler(CommandHandler("pay", pay_command))
    registration_conv = ConversationHandler(
        entry_points=[
            CommandHandler("register", register_start),
            CommandHandler("edit", edit_start),
        ],
        states={
            FIRST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_first_name)],
            LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_last_name)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_age)],
        },
        fallbacks=[CommandHandler("cancel", register_cancel)],
    )

    app.add_handler(registration_conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

