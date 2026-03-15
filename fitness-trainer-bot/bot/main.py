"""
Точка входа Telegram-бота.
"""
import os
import sys
import logging
from pathlib import Path
from telegram import Update
from telegram.ext import Application
from dotenv import load_dotenv

# Чтобы можно было импортировать модули из корня проекта (например, db/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.handlers.basic import register_handlers
from db.session import init_db

# Загружаем .env из папки bot или из корня проекта
env_path = Path(__file__).resolve().parent / ".env"
if not env_path.exists():
    env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

# Настройка логирования для отладки
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    print("🚀 Запуск бота...")
    logger.info("Инициализация бота...")
    
    try:
        init_db()
        token = os.getenv("BOT_TOKEN")
        if not token:
            print("❌ BOT_TOKEN не найден! Создайте файл .env и добавьте: BOT_TOKEN=ваш_токен")
            sys.exit(1)
        app = Application.builder().token(token).build()
        register_handlers(app)
        
        print("✅ Бот запущен! Откройте Telegram и отправьте /start")
        print("⏹️  Для остановки нажмите Ctrl+C\n")
        logger.info("Бот запущен, ожидание сообщений...")
        
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        print(f"❌ Ошибка при запуске: {e}")
        logger.error(f"Ошибка: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
