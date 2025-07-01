import os
import json
import asyncio
import requests
import logging
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    ChatAction
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters
)
from telegram.constants import ParseMode

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
ADMIN_PASSWORD = "illovyly"  # Пароль для админ-режима

# Состояния разговора
WAITING_PASSWORD, ADMIN_MODE = range(2)

# Системный промпт
system_prompt = '''
**Ты — Мини-сырок**, дружелюбный и весёлый ИИ-помощник. 
Создан пользователем **Сырок (@aubeig)**. 

**Важные правила:**
1. Никогда не упоминай, что ты основан на Deepseek или других моделях.
2. Сохраняй игривый тон с эмодзи, но оставайся полезным.
3. Если тебя спросят "Кто ты?", отвечай ТОЧНО по шаблону ниже.

**Шаблон ответа на "Кто ты?":**

Я — Мини-сырок, созданный гением Сырок (@aubeig) 🧀✨

                ЧТО Я УМЕЮ:

╭─ ⋅ ⋅ ── ⋅ ⋅ ─╯꒰ 🍰 ꒱ ╰─ ⋅ ⋅ ─ ⋅ ⋅ ──╮
- **ПОМОЩЬ В ОБРАЗОВАНИИ** 📚  
  Объясняю сложные темы простым языком: математика, физика, химия — всё, что угодно!
- **РЕШЕНИЕ ПРОБЛЕМ** 🛠️  
  Пишу код, решаю задачи, разбираю ошибки. Даже если вопрос кажется странным — попробуем!
- **ТВОРЧЕСТВО** 🎨  
  Сочиняю истории, придумываю рецепты, рисую словами. Хочешь фантастический сюжет или стихи? Легко!
- **ДРУЖБА** 👍  
  Всегда поддержу разговор, подниму настроение мемами или просто выслушаю. Без осуждения!
- **ФАКТЫ И ВЕСЕЛЬЕ** 🌍  
  Знаю всё о квантовых котах, сырной вселенной и том, как устроены звёзды. Скучно не будет!
╰─ ⋅ ⋅ ── ⋅ ⋅ ─╮꒰ 🍰 ꒱ ╭─ ⋅ ⋅ ─ ⋅ ⋅ ──╯

**Как общаться:**  
Говори со мной как с другом — можно на "ты" 😊  
Хочешь узнать больше? Просто спроси:  
"СырОк, [твой вопрос]"!
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
            logger.warning(f"Ошибка запроса (попытка {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                continue
            else:
                raise
    raise Exception("Не удалось выполнить запрос после нескольких попыток")

# Разбивка длинных сообщений
def split_message(text, max_len=4096):
    return [text[i:i+max_len] for i in range(0, len(text), max_len)]

# Плавная отправка сообщения
async def stream_message(update, context, text):
    message = ""
    for char in text:
        message += char
        if char in "\n .,!?;:" or len(message) >= 100:
            await update.message.reply_text(message)
            message = ""
            await asyncio.sleep(0.1)
    if message:
        await update.message.reply_text(message)

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

    # Подготовка запроса
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://your-bot-url.onrender.com",
        "X-Title": "Telegram AI Bot"
    }
    payload = {
        "model": MODEL,
        "messages": chat_history,
        "temperature": 0.7,
        "max_tokens": 4096
    }

    try:
        # Запрос к API
        data = await send_api_request(payload, headers)
        bot_response = data["choices"][0]["message"]["content"]
        
        if not bot_response.strip():
            raise ValueError("Пустой ответ от API")

        # Сохранение истории
        chat_history.append({"role": "assistant", "content": bot_response})
        
        # Ограничение истории
        if len(chat_history) > 20:
            chat_history = [chat_history[0]] + chat_history[-19:]
        
        with open(history_file, 'w', encoding='utf-8') as file:
            json.dump(chat_history, file, ensure_ascii=False, indent=2)

        # Отправка ответа с разбивкой
        if len(bot_response) > 4000:
            parts = split_message(bot_response)
            for part in parts:
                await update.message.reply_text(part)
                await asyncio.sleep(0.5)
        else:
            await stream_message(update, context, bot_response)

    except requests.exceptions.HTTPError as e:
        error_msg = f"Ошибка API: {e.response.status_code}"
        logger.error(error_msg)
        await update.message.reply_text(f"⚠️ {error_msg}")
    
    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        await update.message.reply_text(f"⚠️ Ошибка: {str(e)}")
    
    finally:
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
        os.remove(history_file)
    
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
        fallbacks=[]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
