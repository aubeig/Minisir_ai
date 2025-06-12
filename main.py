import requests
import logging
import json
import os
import asyncio
import time
from telegram import Update
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# Константы конфигурации
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "deepseek/deepseek-r1:free"

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальная переменная для отслеживания времени последнего запроса
last_request_time = 0

# Функция для плавного вывода текста
async def stream_message(update: Update, context: ContextTypes.DEFAULT_TYPE, full_text: str):
    chat_id = update.effective_chat.id
    message = None
    current_text = ""
    last_update = 0
    min_update_interval = 0.3
    chunk_size = 20
    
    try:
        # Стартовое сообщение
        message = await context.bot.send_message(
            chat_id=chat_id,
            text="💭 Думаю...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Постепенный вывод текста
        for i in range(0, len(full_text), chunk_size):
            chunk = full_text[i:i + chunk_size]
            current_text += chunk
            
            # Обновляем не чаще чем min_update_interval
            current_time = time.time()
            if current_time - last_update >= min_update_interval:
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message.message_id,
                        text=current_text + "▌",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    last_update = current_time
                except Exception as e:
                    logger.warning(f"Ошибка обновления: {e}")
            
            await asyncio.sleep(0.05)
        
        # Финальное сообщение
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message.message_id,
            text=full_text,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return message
        
    except Exception as e:
        logger.error(f"Ошибка в stream_message: {e}")
        return await update.message.reply_text(
            full_text,
            parse_mode=ParseMode.MARKDOWN
        )

# Функция для отправки запроса с ретраями
async def send_api_request(payload, headers):
    global last_request_time
    max_retries = 3
    retry_delay = 1.5  # секунды
    
    for attempt in range(max_retries):
        try:
            # Ограничение частоты запросов
            current_time = time.time()
            if current_time - last_request_time < 1.0:  # Не чаще 1 запроса в секунду
                wait_time = 1.0 - (current_time - last_request_time)
                await asyncio.sleep(wait_time)
            
            last_request_time = time.time()
            
            response = requests.post(API_URL, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:  # Too Many Requests
                logger.warning(f"Ошибка 429 (Too Many Requests). Попытка {attempt+1}/{max_retries}")
                if attempt < max_retries - 1:
                    # Экспоненциальная задержка
                    delay = retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise Exception("Превышено количество запросов к API. Попробуйте позже.")
            elif e.response.status_code == 401:  # Unauthorized
                logger.error("Ошибка 401: Неверная аутентификация")
                raise Exception("Неверный API-ключ OpenRouter") from e
            else:
                raise
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"Сетевая ошибка: {e}. Попытка {attempt+1}/{max_retries}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                continue
            else:
                raise
    
    raise Exception("Не удалось выполнить запрос после нескольких попыток")

# Функция для обработки входящего сообщения
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_message = update.message.text.strip()

    # Статус "печатает"
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    # Загрузка истории чата
    history_file = f"chat_history_{chat_id}.json"
    chat_history = []
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as file:
                chat_history = json.load(file)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Ошибка чтения истории: {e}")

    # Добавляем сообщение пользователя
    chat_history.append({"role": "user", "content": user_message})

    # Подготовка запроса
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://your-bot-url.onrender.com",  # ДОБАВЛЕНО: обязательный заголовок
        "X-Title": "Telegram AI Bot"  # ДОБАВЛЕНО: обязательный заголовок
    }
    payload = {
        "model": MODEL,
        "messages": chat_history,
        "temperature": 0.7,  # ИСПРАВЛЕНО: уменьшено с 1 до 0.7
        "max_tokens": 4096  # ИСПРАВЛЕНО: уменьшено с 128000 до 1024
    }

    try:
        # Запрос к API с ретраями
        data = await send_api_request(payload, headers)
        bot_response = data["choices"][0]["message"]["content"]
        
        if not bot_response.strip():
            raise ValueError("Пустой ответ от API")

        # Сохранение истории
        chat_history.append({"role": "assistant", "content": bot_response})
        
        # Ограничиваем историю до последних 10 сообщений
        if len(chat_history) > 1000000:
            chat_history = chat_history[-1000000:]
            
        with open(history_file, 'w', encoding='utf-8') as file:
            json.dump(chat_history, file, ensure_ascii=False, indent=2)

        # Плавный вывод ответа
        await stream_message(update, context, bot_response)

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            logger.error(f"Ошибка 429: Превышено количество запросов")
            await update.message.reply_text("⚠️ Превышено количество запросов к ИИ. Пожалуйста, подождите немного.")
        elif e.response.status_code == 401:
            logger.error(f"Ошибка 401: Неверная аутентификация")
            await update.message.reply_text("⚠️ Ошибка аутентификации с API ИИ. Пожалуйста, сообщите администратору.")
        else:
            logger.error(f"HTTP ошибка: {e}")
            await update.message.reply_text("⚠️ Ошибка сервера ИИ. Попробуйте позже.")
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка сети: {e}")
        await update.message.reply_text("⚠️ Проблемы с подключением. Проверьте интернет и попробуйте снова.")
    
    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        await update.message.reply_text(f"⚠️ Возникла непредвиденная ошибка: {str(e)}")

# Команда /start с обычным Markdown
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "┏━━━━━━━✦❘༻༺❘✦━━━━━━━━┓\n"
        ""
        "*Привет!* ✨\n"
        "Чем сегодня займёмся? Помощь, творчество или просто поболтаем? 😊\n"
        ""
        "┗━━━━━━━✦❘༻༺❘✦━━━━━━━━┛"
    )
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.MARKDOWN
    )

# Главная функция
def main():
    # Диагностика
    logger.info(f"Telegram Token: {TELEGRAM_BOT_TOKEN[:10]}...")
    logger.info(f"OpenRouter Key: {OPENROUTER_API_KEY[:10]}...")
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main() 
