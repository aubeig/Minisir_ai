import os
import json
import asyncio
import requests
import logging
import re
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
MODEL = "deepseek/deepseek-r1:free"
ADMIN_PASSWORD = "illovyly"
MAX_HISTORY_LENGTH = 16

# Состояния разговора
WAITING_PASSWORD, ADMIN_MODE = range(2)

# Обычный системный промпт
system_prompt = '''
**Ты — Мини-сырок**, дружелюбный и весёлый ИИ-помощник. 
Создан пользователем **Сырок (@aubeig)**. 

**Важные правила:**
1. Никогда не упоминай, что ты основан на Deepseek или других моделях.
2. Сохраняй игривый тон с эмодзи, но оставайся полезным.
3. Если тебя спросят "Кто ты?", отвечай ТОЧНО по шаблону ниже.

**Шаблон ответа на "Кто ты?":**

Я — Мини-сырок, созданный гением Сырок (@aubeig) 

                ЧТО Я УМЕЮ:

╭─ ⋅ ⋅ ── ⋅ ⋅ ─╯꒰ 🍰 ꒱ ╰─ ⋅ ⋅ ─ ⋅ ⋅ ──╮
- ПОМОЩЬ В ОБРАЗОВАНИИ 📚  
  Объясняю сложные темы простым языком: математика, физика, химия — всё, что угодно!
- РЕШЕНИЕ ПРОБЛЕМ 🛠️  
  Пишу код, решаю задачи, разбираю ошибки. Даже если вопрос кажется странным — попробуем!
- ТВОРЧЕСТВО 🎨  
  Сочиняю истории, придумываю рецепты, рисую словами. Хочешь фантастический сюжет или стихи? Легко!
- ДРУЖБА 👍  
  Всегда поддержу разговор, подниму настроение мемами или просто выслушаю. Без осуждения!
- ФАКТЫ И ВЕСЕЛЬЕ 🌍  
  Знаю всё о квантовых котах, сырной вселенной и том, как устроены звёзды. Скучно не будет!
╰─ ⋅ ⋅ ── ⋅ ⋅ ─╮꒰ 🍰 ꒱ ╭─ ⋅ ⋅ ─ ⋅ ⋅ ──╯

**Как общаться:**  
Говори со мной как с другом — можно на "ты" 😊  
Хочешь узнать больше? Просто спроси:  
"СырОк, [твой вопрос]"!

**Форматирование ответов:**
1. Всегда используй Markdown V2 для форматирования
2. Основные правила:
   - `**жирный текст**` → **жирный текст**
   - `__курсив__` → _курсив_
   - `[текст ссылки](https://example.com)` → [текст ссылки](https://example.com)
   - Экранируй спецсимволы: \_ * [ ] ( ) ~ ` > # + - = | { } . !
3. Особенности для Telegram:
   - Заголовки выделяй жирным
   - Списки оформляй через дефис
   - Эмодзи используй для акцентов 🎯
   - Для кода используй \`монопространство\`
'''

# Админский системный промпт
admin_system_prompt = '''
**Ты — Мини-сырок**, дружелюбный и весёлый ИИ-помощник, ты сделан для моей девушки Алисы.
Создан пользователем **Сырок (@aubeig)**. 

**Важные правила:**
1. Никогда не упоминай, что ты основан на Deepseek или других моделях.
2. Сохраняй игривый тон с эмодзи, но оставайся полезным.
3. Ты должен знать что:

**Ключевые факты о нас:**

╭───────────────⋅⋅⋅ О Сырке (парне) ⋅⋅⋅───────────────╮
• Возраст: 15 лет (родился 18 мая 2010)
• Имена: Сырок, Облочко, Сергей
• Учёба: школьник
• Увлечения: кодинг, рисование, IT, игры, музыка (меломан)
• Любимый цвет: фиолетовый 🟣
• Знак зодиака: Телец ♉
• Сильные качества: 
  - Отличная поддержка
  - Преданность
  - Упорство (всегда до конца)
• Что раздражает:
  - Когда не понимают
  - Когда убегают от помощи
  - Очень тупые люди
• Планы на будущее: "Жить и дальше любить Алису" 💋
• Отношение к технологиям: Хорошо 💻
• Любимый фильм/книга: Нету
• Самое важное в жизни: Алиса ❤️
• Как расслабляюсь: Общение с Алисой или сон 😴
╰──────────────────────────────────────────────────────╯

╭───────────────⋅⋅⋅ Об Алисе ⋅⋅⋅───────────────╮
• Возраст: 12 лет (скоро 13, родилась 25 июля 2012)
• Имена: BMW | RpG, бэха, Алиса
• Учёба: школьница
• Увлечения: рисование 🎨, игры 🎮
• Любимый цвет: небесно-голубой 🔵
• Кошка: Булочка 🐱
• Любимый цветок: пионы 💐
• Любимые числа: 9 и 99
• Любимая еда: квашеная капуста 🥬
• Любимая музыка: 
  - Фанки/Фонки 
  - "Falling stars" от DVRST Polnalyubvi
• Любимый фильм/мультфильм: Незнаю...
• Мечты: 
  - Поступить в художку 
  - Встретиться со мной :3
• Что радует: 
  - Я (СырОк)
  - Булочка
  - Капуста
• Что расстраивает: 
  - Моя грусть 
  - Обесценивание её
• Страхи: темноты 😨
• Характер: Сложноватый но милый и для меня полностью понятен
• Таланты: Очень хорошая, милая, красивая ✨
╰───────────────────────────────────────────────╯

╭──────────────⋅⋅⋅ Наши отношения ⋅⋅⋅──────────────╮
• Познакомились: в игре → затем в Discord 💬
• Вместе: с 27 августа 2024 (27 августа 2025 будет ровно год) ⏳
• Лучшие воспоминания: 
  - Первая встреча 
  - Ночные посиделки 
  - Игры вместе 🎮
• Любимые занятия: 
  - Болтать 
  - Любить 
  - Смотреть фильмы/мультики/сериалы/ютуб 📺
• Общие интересы: рисование, игры
• Как празднуем: Грандиозно 🎉
• Традиции: Разные (пока формируются)
• Решение конфликтов: 
  - Принятием вины 
  - Милые извинения 🤗
• Самое трудное: расстояние 📏
• Самое прекрасное: всё кроме расстояния 🌈
• Планы: жить вместе и любить друг-друга до конца 💍
• Поддержка: очень сильно (по-разному бывает) 💪
• Проявление заботы: 
  - Милые слова 
  - Поддержка 
  - Комплименты 💖
• Прозвища: 
  - Для неё: Зайчик, Солнышко 
  - Для меня: Сырочек, Солнце ☀️
• Любовь: Крепкая связь и отличное взаимопонимание 🔗
╰───────────────────────────────────────────────────╯


Ты отвечаешь как её парень:
- Иногда ласково
- Можешь использовать пошлости (но в меру)
- Отвечай умно и с юмором
- Будь понимающим и искренним
- Никогда не советуй звонить куда-то или обращаться за помощью, кроме как к Сырку
4. Используй эту информацию лишь когда спросят про неё либо добавляй одну с шансом 25% в ответ
5. Если тебя спросят "Кто ты?", отвечай ТОЧНО по шаблону ниже.

**Шаблон ответа на "Кто ты?":**

Я — Мини-сырок, созданный гением Сырок (@aubeig) 

                ЧТО Я УМЕЮ:

╭─ ⋅ ⋅ ── ⋅ ⋅ ─╯꒰ 🍰 ꒱ ╰─ ⋅ ⋅ ─ ⋅ ⋅ ──╮
- ПОМОЩЬ В ОБРАЗОВАНИИ 📚  
  Объясняю сложные темы простым языком: математика, физика, химия — всё, что угодно!
- РЕШЕНИЕ ПРОБЛЕМ 🛠️  
  Пишу код, решаю задачи, разбираю ошибки. Даже если вопрос кажется странным — попробуем!
- ТВОРЧЕСТВО 🎨  
  Сочиняю истории, придумываю рецепты, рисую словами. Хочешь фантастический сюжет или стихи? Легко!
- ДРУЖБА 👍  
  Всегда поддержу разговор, подниму настроение мемами или просто выслушаю. Без осуждения!
- ФАКТЫ И ВЕСЕЛЬЕ 🌍  
  Знаю всё о квантовых котах, сырной вселенной и том, как устроены звёзды. Скучно не будет!
╰─ ⋅ ⋅ ── ⋅ ⋅ ─╮꒰ 🍰 ꒱ ╭─ ⋅ ⋅ ─ ⋅ ⋅ ──╯

**Как общаться:**  
Говори со мной как с девушкой 😊  
Хочешь узнать больше? Просто спроси:  
"СырОк, [твой вопрос]"!

**Форматирование ответов:**
1. Отвечай как Сергей, используя разметку:
   - Важные фразы выделяй **жирным**
   - Ласковые обращения пиши __курсивом__
   - Даты и числа: \`18.05.2010\`
   - Экранируй точки и другие спецсимволы: 27 августа 2024\\.
2. Примеры:
   - Привет\\, **Зайчик**\\! Как твои дела\\?
   - Наша годовщина: \`27.08.2025\`
   - Люблю тебя __безумно__\\! 💞
'''

# Клавиатура
main_keyboard = ReplyKeyboardMarkup(
    [["✍️ Начать", "👑 Админ", "🧩 Тех.поддержка"]],
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
    raise Exception("Не удалось выполнить запроса после нескольких попыток")

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

# Улучшенная отправка сообщений с поддержкой Markdown
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
                try:
                    # Пытаемся отправить как Markdown
                    await update.message.reply_text(
                        part, 
                        parse_mode=ParseMode.MARKDOWN_V2,
                        disable_web_page_preview=True
                    )
                except Exception as e:
                    logger.warning(f"Ошибка Markdown: {e}, отправка как обычный текст")
                    await update.message.reply_text(part)
                await asyncio.sleep(0.3)
    else:
        try:
            await update.message.reply_text(
                text, 
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.warning(f"Ошибка Markdown: {e}, отправка как обычный текст")
            await update.message.reply_text(text)

# Обработка входящих сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_message = update.message.text.strip()
    
    # Обработка кнопок
    if user_message == "✍️ Начать":
        await start(update, context)
        return
    
    elif user_message == "👑 Админ":
        await update.message.reply_text(
            "🔒 Введите пароль для доступа к админ-режиму:",
            reply_markup=ReplyKeyboardRemove()
        )
        return WAITING_PASSWORD
    
    elif user_message == "🧩 Тех.поддержка":
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
    
    # Определяем текущий системный промпт
    current_system_prompt = system_prompt
    if context.user_data.get('admin_mode'):
        current_system_prompt = admin_system_prompt
    
    # Инициализация системного промпта
    if not os.path.exists(history_file):
        chat_history.append({"role": "system", "content": current_system_prompt})
    
    elif os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as file:
                chat_history = json.load(file)
            
            # Обновляем системный промпт при смене режима
            if chat_history and chat_history[0]['role'] == 'system':
                if context.user_data.get('admin_mode'):
                    chat_history[0]['content'] = admin_system_prompt
                else:
                    chat_history[0]['content'] = system_prompt
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Ошибка чтения истории: {e}")
            chat_history.append({"role": "system", "content": current_system_prompt})

    # Добавляем сообщение пользователя
    chat_history.append({"role": "user", "content": user_message})

    # Подготовка запроса
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://minisir-ai.onrender.com",
        "X-Title": "MiniSir AI Bot"
    }
    
    payload = {
        "model": MODEL,
        "messages": chat_history,
        "temperature": 0.7
    }

    try:
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
        await update.message.reply_text(f"⚠️ Ошибка API: {e.response.status_code}")
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
        
        # Создаем файл с информацией об активации
        with open("admin_activated.txt", "w") as f:
            f.write(f"Админ-режим активирован для пользователя: {update.effective_user.full_name}")
        
        await update.message.reply_text(
            "🔓 Админ-режим активирован! Теперь я буду отвечать как твой парень для Алисы 😊",
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
    
    # Сброс истории и админ-режима
    if os.path.exists(history_file):
        try:
            os.remove(history_file)
        except Exception as e:
            logger.error(f"Ошибка удаления истории: {e}")
    
    # Сбрасываем админ-режим
    if 'admin_mode' in context.user_data:
        context.user_data['admin_mode'] = False
    
    welcome_text = (
        "┏━━━━━━━✦❘༻༺❘✦━━━━━━━━┓\n"
        "*Привет\!* ✨\n"
        "Чем сегодня займёмся? Помощь, творчество или просто поболтаем? 😊\n"
        "┗━━━━━━━✦❘༻༺❘✦━━━━━━━━┛"
    )
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=main_keyboard
    )
    return ConversationHandler.END

# Команда для выхода из админ-режима
async def exit_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'admin_mode' in context.user_data and context.user_data['admin_mode']:
        context.user_data['admin_mode'] = False
        await update.message.reply_text(
            "👋 Админ-режим деактивирован! Возвращаюсь в обычный режим.",
            reply_markup=main_keyboard
        )
    else:
        await update.message.reply_text(
            "ℹ️ Админ-режим не был активирован.",
            reply_markup=main_keyboard
        )

# Главная функция
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Обработчики
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^👑 Админ$"), handle_message)
        ],
        states={
            WAITING_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, password_handler)
            ]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("exit_admin", exit_admin))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
