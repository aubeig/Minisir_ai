# main.py
import logging
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ConversationHandler
)
from config import TELEGRAM_BOT_TOKEN
from handlers import (
    start, tech_support, show_models, set_model, main_handler,
    admin_prompt, handle_password, exit_admin, search_handler,
    SELECTING_ACTION, WAITING_PASSWORD, ADMIN_MODE, WAITING_SEARCH_QUERY
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # ConversationHandler для управления состояниями (админка, поиск и т.д.)
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
                MessageHandler(filters.TEXT & ~filters.COMMAND, main_handler), # Админ пишет обычный текст
            ],
            WAITING_SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_handler)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(conv_handler)
    # Обработчик для всех текстовых сообщений, когда нет активного состояния
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_handler))
    
    logger.info("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
