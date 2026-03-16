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

from db.session import (
    upsert_user,
    get_user_by_telegram_id,
    get_active_subscription,
    create_free_trial_if_eligible,
    increment_trainer_usage,
)
from bot.services.fitness_ai import ask_fitness_trainer


MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("Тарифы"), KeyboardButton("Мой тариф"), KeyboardButton("Чат с тренером")],
        [KeyboardButton("/start"), KeyboardButton("/help")],
        [KeyboardButton("/register"), KeyboardButton("/cancel")],
    ],
    resize_keyboard=True,
)


# Пробный тариф выдаётся автоматически зарегистрированным (2 коротких вопроса). Не покупается.
# Платные тарифы: 2 = 10 вопросов, 3 = безлимит на месяц
TARIFFS = {
    "2": {
        "code": "paid_10",
        "name": "10 вопросов тренеру",
        "price": 100.0,
        "description": "10 вопросов AI-тренеру — 100 ₽",
    },
    "3": {
        "code": "unlimited",
        "name": "Чат с тренером на месяц",
        "price": 1000.0,
        "description": "Безлимитный чат с AI-тренером на 30 дней — 1000 ₽",
    },
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = (
        "Привет! Я фитнес-бот с AI-тренером.\n\n"
        "🤖 Как пользоваться тренером:\n"
        "1. Зарегистрируйтесь — /register (получите 2 бесплатных коротких вопроса).\n"
        "2. Нажмите «Чат с тренером» или отправьте /trainer — задавайте вопросы, пишите сообщения.\n"
        "3. Выйти из диалога — /cancel.\n\n"
        "📋 Кнопка «Мой тариф» — остаток вопросов. «Тарифы» — список тарифов и оплата (/pay 2 или /pay 3)."
    )
    await update.message.reply_text(welcome, reply_markup=MAIN_KEYBOARD)




async def menu_buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий кнопок «Тарифы» и «Мой тариф»."""
    text = (update.message.text or "").strip()
    if text == "Тарифы":
        await tariffs_command(update, context)
    elif text == "Мой тариф":
        await my_tariff_command(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Список команд:\n"
        "/start - начать работу с ботом\n"
        "/help - показать это сообщение с командами\n"
        "/register - регистрация (имя, фамилия, возраст)\n"
        "/edit - редактировать сохранённые данные\n"
        "/tariffs - посмотреть доступные тарифы\n"
        "/mytariff - мой тариф и остаток вопросов\n"
        "/pay <номер> - оплатить тариф (/pay 2 или /pay 3)\n"
        "/trainer - диалог с фитнес-тренером (AI). Выход — /cancel\n"
        "/cancel - выйти из диалога с тренером или отменить регистрацию\n"
    )
    await update.message.reply_text(text, reply_markup=MAIN_KEYBOARD)


# Состояния диалога регистрации
FIRST_NAME, LAST_NAME, AGE = range(3)
# Состояние диалога с тренером (AI)
TRAINER_CHAT = 10


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
        "Тарифы AI-тренера:\n\n"
        "🆓 Пробный (только для зарегистрированных)\n"
        "   • 2 коротких вопроса тренеру бесплатно\n"
        "   • Сначала /register, затем /trainer\n\n"
        "2️⃣ 10 вопросов — 100 ₽\n"
        "   • 10 вопросов AI-тренеру\n"
        "   • Оплата: /pay 2\n\n"
        "3️⃣ Чат на месяц — 1 000 ₽\n"
        "   • Безлимитный чат с тренером 30 дней\n"
        "   • Оплата: /pay 3"
    )
    await update.message.reply_text(text, reply_markup=MAIN_KEYBOARD)


async def pay_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Укажите номер тарифа: /pay 2 (10 вопросов — 100 ₽) или /pay 3 (чат на месяц — 1000 ₽)."
        )
        return

    tariff_key = context.args[0].strip()
    tariff = TARIFFS.get(tariff_key)
    if not tariff:
        await update.message.reply_text(
            "Неизвестный тариф. Используйте /pay 2 или /pay 3. Список: /tariffs"
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


async def my_tariff_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать текущий тариф пользователя и остаток вопросов."""
    tg_user = update.effective_user
    if not tg_user or not tg_user.id:
        await update.message.reply_text("Не удалось определить пользователя.")
        return
    telegram_id = tg_user.id
    sub = get_active_subscription(telegram_id)
    if not sub:
        sub = create_free_trial_if_eligible(telegram_id)
    if not sub:
        if not get_user_by_telegram_id(telegram_id):
            await update.message.reply_text(
                "У вас нет активного тарифа.\n\n"
                "Зарегистрируйтесь (/register) — получите пробный тариф: 2 вопроса тренеру.\n"
                "Или выберите платный тариф: /tariffs"
            )
        else:
            await update.message.reply_text(
                "У вас нет активного тарифа (лимит исчерпан).\n\n"
                "Купите тариф: /tariffs\n"
                "Оплата: /pay 2 (10 вопросов — 100 ₽) или /pay 3 (чат на месяц — 1000 ₽)"
            )
        return
    code = sub.get("tariff_code") or ""
    name = {"free_trial": "Пробный", "paid_10": "10 вопросов", "unlimited": "Чат на месяц"}.get(
        code, code
    )
    limit = sub.get("questions_limit")
    used = sub.get("questions_used") or 0
    if limit is not None:
        left = limit - used
        text = f"Ваш тариф: {name}\nИспользовано вопросов: {used} из {limit}\nОсталось: {left}"
    else:
        expires_at = sub.get("expires_at") or ""
        text = f"Ваш тариф: {name}\nБезлимитный чат с тренером до {expires_at[:10] if expires_at else '—'}"
    await update.message.reply_text(text, reply_markup=MAIN_KEYBOARD)


def _trainer_has_key() -> bool:
    return bool(
        (os.getenv("GROQ_API_KEY") or "").strip()
        or (os.getenv("OPENROUTER_API_KEY") or "").strip()
        or (os.getenv("GEMINI_API_KEY") or "").strip()
    )


def _get_trainer_subscription(telegram_id: int) -> tuple:
    """
    Возвращает (subscription, error_message).
    subscription — активная подписка с лимитом; error_message — если нельзя пользоваться тренером.
    """
    sub = get_active_subscription(telegram_id)
    if sub:
        return sub, None
    sub = create_free_trial_if_eligible(telegram_id)
    if sub:
        return sub, None
    if not get_user_by_telegram_id(telegram_id):
        return None, "Сначала зарегистрируйтесь: /register — тогда получите 2 бесплатных вопроса тренеру."
    return None, "Лимит вопросов исчерпан. Купите тариф: /tariffs и оплатите /pay 2 или /pay 3."


# Для пробного тарифа ограничиваем длину вопроса (короткие вопросы)
FREE_TRIAL_MAX_QUESTION_LEN = 200


async def trainer_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Вход в диалог с тренером: /trainer или /trainer вопрос. Проверка тарифа."""
    if not _trainer_has_key():
        await update.message.reply_text(
            "Тренер (AI) не настроен. Добавьте в bot/.env один из ключей (OPENROUTER_API_KEY, GROQ_API_KEY, GEMINI_API_KEY)."
        )
        return ConversationHandler.END
    tg_user = update.effective_user
    if not tg_user or not tg_user.id:
        return ConversationHandler.END
    telegram_id = tg_user.id
    sub, err = _get_trainer_subscription(telegram_id)
    if err:
        await update.message.reply_text(err)
        return ConversationHandler.END
    question = " ".join(context.args).strip() if context.args else ""
    if question:
        if sub.get("tariff_code") == "free_trial" and len(question) > FREE_TRIAL_MAX_QUESTION_LEN:
            question = question[:FREE_TRIAL_MAX_QUESTION_LEN].rstrip() + "…"
        await update.message.reply_chat_action("typing")
        answer = await ask_fitness_trainer(question)
        if answer:
            if len(answer) > 4096:
                answer = answer[:4090] + "\n…"
            await update.message.reply_text(answer)
            increment_trainer_usage(telegram_id, sub["id"])
            left = ""
            if sub.get("questions_limit") is not None:
                used = sub.get("questions_used", 0) + 1
                left = f" Осталось вопросов: {sub['questions_limit'] - used}."
            if left:
                await update.message.reply_text(left.strip())
        else:
            await update.message.reply_text(
                "Тренер временно недоступен (лимит или сеть). Попробуйте позже или /cancel."
            )
        return TRAINER_CHAT
    limit_info = "без лимита" if sub.get("questions_limit") is None else f"осталось {sub['questions_limit'] - sub.get('questions_used', 0)} вопросов"
    await update.message.reply_text(
        f"Диалог с тренером ({limit_info}). Пишите сообщения — ответы придут сюда. Выход: /cancel"
    )
    return TRAINER_CHAT


async def trainer_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сообщение в режиме тренера: проверка тарифа, списание вопроса, ответ AI."""
    text = (update.message.text or "").strip()
    if not text:
        return TRAINER_CHAT
    tg_user = update.effective_user
    if not tg_user or not tg_user.id:
        return TRAINER_CHAT
    telegram_id = tg_user.id
    sub, err = _get_trainer_subscription(telegram_id)
    if err:
        await update.message.reply_text(err + "\nВыход из диалога: /cancel")
        return TRAINER_CHAT
    if sub.get("tariff_code") == "free_trial" and len(text) > FREE_TRIAL_MAX_QUESTION_LEN:
        text = text[:FREE_TRIAL_MAX_QUESTION_LEN].rstrip() + "…"
    await update.message.reply_chat_action("typing")
    answer = await ask_fitness_trainer(text)
    if not answer:
        await update.message.reply_text(
            "Тренер временно недоступен. Попробуйте позже или /cancel для выхода."
        )
        return TRAINER_CHAT
    if len(answer) > 4096:
        answer = answer[:4090] + "\n…"
    await update.message.reply_text(answer)
    increment_trainer_usage(telegram_id, sub["id"])
    if sub.get("questions_limit") is not None:
        used = sub.get("questions_used", 0) + 1
        left = sub["questions_limit"] - used
        if left >= 0:
            await update.message.reply_text(f"Осталось вопросов: {left}.")
    return TRAINER_CHAT


async def trainer_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Диалог с тренером завершён.")
    return ConversationHandler.END


def register_handlers(app: Application) -> None:
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("tariffs", tariffs_command))
    app.add_handler(CommandHandler("mytariff", my_tariff_command))
    app.add_handler(CommandHandler("pay", pay_command))
    trainer_conv = ConversationHandler(
        entry_points=[
            CommandHandler("trainer", trainer_start),
            MessageHandler(filters.Regex("^Чат с тренером$"), trainer_start),
        ],
        states={
            TRAINER_CHAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, trainer_message)],
        },
        fallbacks=[CommandHandler("cancel", trainer_cancel)],
    )
    app.add_handler(trainer_conv)
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
    app.add_handler(MessageHandler(filters.Regex("^(Тарифы|Мой тариф)$"), menu_buttons_handler))
    

