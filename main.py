import os
import json
import asyncio
import requests
import logging
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters
)
from telegram.constants import ChatAction, ParseMode

# Настройка логгера
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "mistralai/mistral-7b-instruct:free"
ADMIN_PASSWORD = "illovyly"
MAX_HISTORY_LENGTH = 6  # Уменьшено для соответствия ограничениям токенов

# Состояния разговора
WAITING_PASSWORD, ADMIN_MODE = range(2)

# Системный промпт (упрощенная версия для тестирования)
system_prompt = '''
Ты — Мини-сырок, дружелюбный ИИ-помощник. Создан пользователем Сырок (@aubeig).
Отвечай кратко и по делу. Сохраняй дружелюбный тон.
'''

# Клавиатура
main_keyboard = ReplyKeyboardMarkup(
    [["НАЧАТЬ", "Админ", "Тех.поддержка"]],
    resize_keyboard=True,
    input_field_placeholder="Выберите действие..."
)

# Функция для отправки запросов с повторными попытками
async def send_api_request(payload, headers, max_retries=3, retry_delay=2):
    for attempt in range(max_retries):
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка запроса (попытка {attempt + 1}): {e}")
            if e.response is not None:
                logger.error(f"Тело ответа: {e.response.text}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                continue
            else:
                raise
    raise Exception("Не удалось выполнить запрос после нескольких попыток")

# Разбивка длинных сообщений
def split_message(text, max_len=4096):
    parts = []
    while text:
        if len(text) > max_len:
            split_index = text.rfind('\n', 0, max_len)
            if split_index == -1:
                split_index = text.rfind('. ', 0, max_len)
            if split_index == -1:
                split_index = text.rfind(' ', 0, max_len)
            if split_index == -1:
                split_index = max_len
                
            parts.append(text[:split_index].strip())
            text = text[split_index:].strip()
        else:
            parts.append(text.strip())
            break
    return parts

# Улучшенная отправка сообщений
async def send_response(update, context, text):
    """Отправляет ответ пользователю с автоматической разбивкой"""
    if not text.strip():
        logger.warning("Попытка отправить пустое сообщение")
        return
    
    # Разбиваем длинные сообщения
    if len(text) > 4000:
        parts = split_message(text)
        for part in parts:
            if part.strip():
                await update.message.reply_text(part)
                await asyncio.sleep(0.3)
    else:
        # Отправляем короткие сообщения целиком
        await update.message.reply_text(text)

# Обработка входящих сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_message = update.message.text.strip()
    
    # Обработка кнопок
    if user_message == "НАЧАТЬ":
        await start(update, context)
        return
    
    elif user_message == "Админ":
        await update.message.reply_text(
            "🔒 Введите пароль для доступа к админ-режиму:",
            reply_markup=ReplyKeyboardRemove()
        )
        return WAITING_PASSWORD
    
    elif user_message == "Тех.поддержка":
        await update.message.reply_text(
            "🛠️ Свяжитесь с техподдержкой:\nhttps://t.me/Aubeig",
            reply_markup=main_keyboard
        )
        return
    
    # Статус "печатает"
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    # Загрузка истории чата
    history_file = f"chat_history_{chat_id}.json"
    chat_history = []
    
    # Инициализация системного промпта
    if not os.path.exists(history_file):
        chat_history.append({"role": "system", "content": system_prompt})
    
    elif os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as file:
                chat_history = json.load(file)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Ошибка чтения истории: {e}")
            chat_history.append({"role": "system", "content": system_prompt})

    # Добавляем сообщение пользователя
    chat_history.append({"role": "user", "content": user_message})

    # Подготовка запроса (исправлено для соответствия API)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://minisir-ai.onrender.com",  # Обновленный URL
        "X-Title": "MiniSir AI Bot"
    }
    
    # Важно: удаляем max_tokens для бесплатных моделей
    payload = {
        "model": MODEL,
        "messages": chat_history,
        "temperature": 0.7,
        # "max_tokens": 1024  # Убрано для бесплатных моделей
    }

    try:
        logger.info(f"Отправка запроса к API: {json.dumps(payload, indent=2, ensure_ascii=False)}")
        
        # Запрос к API
        data = await send_api_request(payload, headers)
        bot_response = data["choices"][0]["message"]["content"]
        
        # Проверка на пустой ответ
        if not bot_response or not bot_response.strip():
            logger.warning("API вернул пустой ответ")
            await update.message.reply_text("🤔 Я не смог придумать ответ. Попробуй задать вопрос иначе!")
            return

        # Сохранение истории
        chat_history.append({"role": "assistant", "content": bot_response})
        
        # Ограничение истории
        if len(chat_history) > MAX_HISTORY_LENGTH:
            # Сохраняем системный промпт и последние сообщения
            system_msg = chat_history[0]
            recent_msgs = chat_history[-(MAX_HISTORY_LENGTH-1):]
            chat_history = [system_msg] + recent_msgs
        
        with open(history_file, 'w', encoding='utf-8') as file:
            json.dump(chat_history, file, ensure_ascii=False, indent=2)

        # Отправляем ответ пользователю
        await send_response(update, context, bot_response)

    except requests.exceptions.HTTPError as e:
        error_msg = f"Ошибка API: {e.response.status_code}"
        logger.error(f"{error_msg}, Тело ответа: {e.response.text}")
        await update.message.reply_text(f"⚠️ Ошибка API: {e.response.status_code}. Проверьте логи.")
    
    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        await update.message.reply_text(f"⚠️ Ошибка: {str(e)}")
    
    finally:
        # Всегда возвращаем клавиатуру
        if update.effective_chat:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Чем еще могу помочь?",
                reply_markup=main_keyboard
            )

# Обработка пароля
async def password_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    
    if user_input == ADMIN_PASSWORD:
        # Активация админ-режима
        context.user_data['admin_mode'] = True
        await update.message.reply_text(
            "🔓 Админ-режим активирован!",
            reply_markup=main_keyboard
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ Неверный пароль! Попробуйте еще раз или выберите действие:",
            reply_markup=main_keyboard
        )
        return ConversationHandler.END

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    history_file = f"chat_history_{chat_id}.json"
    
    # Сброс истории
    if os.path.exists(history_file):
        try:
            os.remove(history_file)
        except Exception as e:
            logger.error(f"Ошибка удаления истории: {e}")
    
    welcome_text = (
        "┏━━━━━━━✦❘༻༺❘✦━━━━━━━━┓\n"
        "*Привет!* ✨\n"
        "Чем сегодня займёмся? Помощь, творчество или просто поболтаем? 😊\n"
        "┗━━━━━━━✦❘༻༺❘✦━━━━━━━━┛"
    )
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_keyboard
    )
    return ConversationHandler.END

# Главная функция
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Обработчики
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^Админ$"), handle_message)
        ],
        states={
            WAITING_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, password_handler)
            ]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
