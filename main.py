# main.py
import logging
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ConversationHandler
)
from flask import Flask
from threading import Thread
import os

# Импортируем переменные из config, а функции из handlers
from config import TELEGRAM_BOT_TOKEN, SELECTING_ACTION, WAITING_PASSWORD, ADMIN_MODE, WAITING_SEARCH_QUERY
from handlers import (
    start, tech_support, show_models, set_model, main_handler,
    admin_prompt, handle_password, exit_admin, search_handler
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---
flask_app = Flask(__name__)
@flask_app.route('/')
def index():
    return "Бот жив!", 200

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    flask_app.run(host='0.0.0.0', port=port)


def main() -> None:
    # Запускаем веб-сервер в отдельном потоке
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # Запускаем бота
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_ACTION: [
                MessageHandler(filters.Regex("^✍️ Начать$"), main_handler),
                MessageHandler(filters.Regex("^👑 Админ$"), admin_prompt),
                MessageHandler(filters.Regex("^🧩 Тех\.поддержка$"), tech_support),
                MessageHandler(filters.Regex("^🧠 Модели$"), show_models),
                MessageHandler(filters.Regex("^Мини-Сырок"), set_model),
                MessageHandler(filters.Regex("^🔍 Поиск в Google$"), lambda u, c: WAITING_SEARCH_QUERY),
                MessageHandler(filters.Regex("^🔙 Назад$"), start),
            ],
            WAITING_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_password)],
            ADMIN_MODE: [
                MessageHandler(filters.Regex("^🔓 Выйти из админа$"), exit_admin),
                MessageHandler(filters.TEXT & ~filters.COMMAND, main_handler),
            ],
            WAITING_SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_handler)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_handler))
    
    logging.info("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
