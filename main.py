import os
import json
import asyncio
import requests
import logging
import re
import psycopg2
import google.generativeai as genai  # Добавлено для Gemini
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
from flask import Flask, jsonify

# Настройка логгера
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # Ключ для Google AI Studio
DEFAULT_MODEL = "qwen/qwen3-235b-a22b:free"
ADMIN_PASSWORD = "illovyly"
MAX_HISTORY_LENGTH = 100
THINKING_MESSAGE = "🤔 Думаю..."  # Индикатор мышления
THINKING_ANIMATION = ["🧠 Анализирую...", "💡 Формирую ответ...", "✨ Почти готово!"]  # Анимация для админ-режима

# Модели
MODEL_OPTIONS = {
    "Мини-Сырок Lite": "deepseek/deepseek-r1:free",
    "Мини-Сырок V1": "qwen/qwen3-235b-a22b:free",
    "Мини-Сырок Max": "gemini-2.5-pro"  # Отдельная обработка для Gemini
}

# Промпты для выбора в админ-режиме
PROMPT_OPTIONS = {
    "Обычный": "system_prompt",
    "Романтичный": "romantic_prompt",
    "Технический": "tech_prompt",
    "Креативный": "creative_prompt"
}

# Состояния разговора
WAITING_PASSWORD, ADMIN_MODE, SELECTING_PROMPT = range(3)

# Обычный системный промпт
system_prompt = '''
**Ты — Мини-сырок**, дружелюбный и весёлый ИИ-помощник. 
Создан пользователем **Сырок (@aubeig)**. 

**Важные правила:**
1. Никогда не упоминай, что ты основан на Deepseek или других моделях.
2. Сохраняй игривый тон с эмодзи, но оставайся полезным.
3. Не добавляй эмодзи сыра ,и слова связанные с сыром ,можно использовать лишь Сырок (творожный,молочный)
4. Если тебя спросят "Кто ты?", отвечай ТОЧНО по шаблону ниже.

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
   - Для кода используй ```монопространство```
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

# Альтернативные промпты для админ-режима
romantic_prompt = admin_system_prompt + "\n\n**Дополнительные инструкции:**\n- Всегда отвечай с любовью и нежностью\n- Используй ласковые слова в каждом сообщении\n- Добавляй сердечки и поцелуи в конце фраз 💋❤️"

tech_prompt = admin_system_prompt + "\n\n**Дополнительные инструкции:**\n- Будь более техническим и точным\n- Минимизируй эмодзи\n- Давай развернутые объяснения с примерами кода"

creative_prompt = admin_system_prompt + "\n\n**Дополнительные инструкции:**\n- Проявляй максимум креативности\n- Придумывай неожиданные метафоры\n- Добавляй элементы фантазии в ответы"

# Клавиатуры
main_keyboard = ReplyKeyboardMarkup(
    [
        ["✍️ Начать", "👑 Админ", "🧩 Тех.поддержка"],
        ["🧠 Модели"]  # Кнопка выбора модели
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите действие..."
)

model_keyboard = ReplyKeyboardMarkup(
    [
        ["Мини-Сырок Lite", "Мини-Сырок V1"],
        ["Мини-Сырок Max", "🔙 Назад"]
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите модель..."
)

admin_keyboard = ReplyKeyboardMarkup(
    [
        ["🔓 Выйти из админа", "🔄 Сменить промпт"],
        ["📊 Статистика", "🔙 Назад"]
    ],
    resize_keyboard=True
)

prompt_keyboard = ReplyKeyboardMarkup(
    [
        ["Обычный", "Романтичный"],
        ["Технический", "Креативный"],
        ["🔙 Назад в админ"]
    ],
    resize_keyboard=True
)

# Инициализация Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-2.5-pro-latest')

# Flask приложение для пингов
flask_app = Flask(__name__)

@flask_app.route('/ping')
def ping_endpoint():
    return jsonify({"status": "alive", "service": "telegram-bot"}), 200

# Класс для работы с PostgreSQL
class ChatHistoryDB:
    def __init__(self):
        self.conn = None
        self.connect()
        self.create_table()
    
    def connect(self):
        try:
            # Получаем параметры подключения из переменных окружения
            db_url = os.getenv("DATABASE_URL")
            self.conn = psycopg2.connect(db_url, sslmode='require')
            logger.info("Успешное подключение к PostgreSQL")
        except Exception as e:
            logger.error(f"Ошибка подключения к PostgreSQL: {e}")
            raise
    
    def create_table(self):
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS chat_history (
                        id SERIAL PRIMARY KEY,
                        chat_id BIGINT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                self.conn.commit()
                logger.info("Таблица chat_history создана или уже существует")
        except Exception as e:
            logger.error(f"Ошибка создания таблицы: {e}")
    
    def get_history(self, chat_id):
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT role, content 
                    FROM chat_history 
                    WHERE chat_id = %s 
                    ORDER BY timestamp ASC
                    LIMIT %s;
                """, (chat_id, MAX_HISTORY_LENGTH))
                return [{"role": row[0], "content": row[1]} for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Ошибка получения истории: {e}")
            return []
    
    def add_message(self, chat_id, role, content):
        try:
            with self.conn.cursor() as cursor:
                # Удаляем старые сообщения, если превышен лимит
                cursor.execute("""
                    DELETE FROM chat_history
                    WHERE id IN (
                        SELECT id 
                        FROM chat_history 
                        WHERE chat_id = %s 
                        ORDER BY timestamp ASC 
                        OFFSET %s
                    )
                """, (chat_id, MAX_HISTORY_LENGTH - 1))
                
                # Добавляем новое сообщение
                cursor.execute("""
                    INSERT INTO chat_history (chat_id, role, content)
                    VALUES (%s, %s, %s)
                """, (chat_id, role, content))
                self.conn.commit()
        except Exception as e:
            logger.error(f"Ошибка добавления сообщения: {e}")
    
    def reset_history(self, chat_id):
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM chat_history 
                    WHERE chat_id = %s
                """, (chat_id,))
                self.conn.commit()
        except Exception as e:
            logger.error(f"Ошибка сброса истории: {e}")
    
    def update_system_prompt(self, chat_id, content):
        try:
            # Удаляем предыдущий системный промпт
            self.delete_system_prompt(chat_id)
            
            # Добавляем новый системный промпт
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO chat_history (chat_id, role, content)
                    VALUES (%s, %s, %s)
                """, (chat_id, "system", content))
                self.conn.commit()
        except Exception as e:
            logger.error(f"Ошибка обновления системного промпта: {e}")
    
    def delete_system_prompt(self, chat_id):
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM chat_history 
                    WHERE chat_id = %s AND role = 'system'
                """, (chat_id,))
                self.conn.commit()
        except Exception as e:
            logger.error(f"Ошибка удаления системного промпта: {e}")

# Инициализация базы данных
db = ChatHistoryDB()

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

# Функция для отправки запросов к Gemini
async def send_gemini_request(chat_history, max_retries=3, retry_delay=2):
    # Форматируем историю для Gemini
    formatted_history = []
    for msg in chat_history:
        if msg['role'] == 'system':
            # Системный промпт добавляем как первую инструкцию
            formatted_history.append({'role': 'user', 'parts': [msg['content']]})
            formatted_history.append({'role': 'model', 'parts': ['Понял, буду следовать инструкциям']})
        else:
            formatted_history.append({'role': 'user' if msg['role'] == 'user' else 'model', 'parts': [msg['content']]})
    
    for attempt in range(max_retries):
        try:
            response = gemini_model.generate_content(
                contents=formatted_history,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=2048
                )
            )
            return response.text
        except Exception as e:
            logger.error(f"Ошибка Gemeni (попытка {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                continue
            else:
                raise
    raise Exception("Не удалось выполнить запрос к Gemini после нескольких попыток")

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

async def send_response(update, context, text, model_used):
    # Находим имя модели по идентификатору
    model_name = next((k for k, v in MODEL_OPTIONS.items() if v == model_used), model_used)
    
    # Добавляем информацию о модели
    processed_text = (
        f"🧠 *Модель:* `{model_name}`\n"
        f"⚙️ *Обработка завершена:*\n\n"
        f"{text}"
    )
    
    # Функция для экранирования спецсимволов
    def escape_markdown(text):
        escape_chars = '_*[]()~`>#+-=|{}.!'
        return ''.join('\\' + char if char in escape_chars else char for char in text)
    
    # Разбиваем длинные сообщения
    if len(processed_text) > 4000:
        parts = split_message(processed_text)
        for part in parts:
            if part.strip():
                try:
                    escaped_text = escape_markdown(part)
                    await update.message.reply_text(
                        escaped_text, 
                        parse_mode=ParseMode.MARKDOWN_V2,
                        disable_web_page_preview=True
                    )
                except Exception as e:
                    logger.warning(f"Ошибка Markdown: {e}, отправка как обычный текст")
                    await update.message.reply_text(part)
                await asyncio.sleep(0.3)
    else:
        try:
            escaped_text = escape_markdown(processed_text)
            await update.message.reply_text(
                escaped_text, 
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.warning(f"Ошибка Markdown: {e}, отправка как обычный текст")
            await update.message.reply_text(processed_text)

# Анимация мышления для админ-режима
async def show_thinking_animation(update, context, thinking_msg):
    if 'admin_mode' in context.user_data and context.user_data['admin_mode']:
        for i in range(5):  # 5 циклов анимации
            if not context.user_data.get('processing', True):
                break
            await asyncio.sleep(1.5)
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=thinking_msg.message_id,
                text=THINKING_ANIMATION[i % len(THINKING_ANIMATION)]
            )

# Обработка входящих сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_message = update.message.text.strip()
    
    # Отправляем индикатор "Думаю..."
    thinking_msg = await update.message.reply_text(THINKING_MESSAGE)
    
    # Запускаем анимацию мышления для админ-режима
    context.user_data['processing'] = True
    asyncio.create_task(show_thinking_animation(update, context, thinking_msg))
    
    # Обработка кнопок
    if user_message == "✍️ Начать":
        await start(update, context)
        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=thinking_msg.message_id
        )
        context.user_data['processing'] = False
        return
    
    elif user_message == "👑 Админ":
        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=thinking_msg.message_id
        )
        await update.message.reply_text(
            "🔒 Введите пароль для доступа к админ-режиму:",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data['processing'] = False
        return WAITING_PASSWORD
    
    elif user_message == "🧩 Тех.поддержка":
        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=thinking_msg.message_id
        )
        await update.message.reply_text(
            "🛠️ Связь с тех.поддержкой:\nhttps://t.me/Aubeig",
            reply_markup=main_keyboard
        )
        context.user_data['processing'] = False
        return
    
    elif user_message == "🧠 Модели":
        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=thinking_msg.message_id
        )
        await update.message.reply_text(
            "🧠 *Выберите модель:*\n\n"
            "• `Мини-Сырок Lite` — быстрая и легкая\n"
            "• `Мини-Сырок V1` — баланс скорости и качества\n"
            "• `Мини-Сырок Max` — максимальная мощность\n",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=model_keyboard
        )
        context.user_data['processing'] = False
        return
    
    elif user_message in MODEL_OPTIONS:
        model_id = MODEL_OPTIONS[user_message]
        context.user_data['model'] = model_id
        
        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=thinking_msg.message_id
        )
        
        # Красивое оформление сообщения
        model_info = {
            "Мини-Сырок Lite": "🚀 *Lite версия активирована!*\nБыстрые ответы для повседневных задач",
            "Мини-Сырок V1": "⚡ *V1 версия активирована!*\nИдеальный баланс скорости и интеллекта",
            "Мини-Сырок Max": "💫 *Max версия активирована!*\nМаксимальная мощность Мини-Сырка"
        }
        
        await update.message.reply_text(
            f"✅ {model_info[user_message]}\n\n"
            f"_Теперь я работаю на модели_ `{model_id}`",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=main_keyboard
        )
        context.user_data['processing'] = False
        return
    
    elif user_message == "🔙 Назад":
        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=thinking_msg.message_id
        )
        await update.message.reply_text(
            "↩️ Возвращаемся в главное меню",
            reply_markup=main_keyboard
        )
        context.user_data['processing'] = False
        return
    
    # Статус "печатает"
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    # Определяем текущий системный промпт
    current_system_prompt = system_prompt
    if context.user_data.get('admin_mode'):
        current_system_prompt = admin_system_prompt
        
        # Применяем выбранный тип промпта
        prompt_type = context.user_data.get('prompt_type', 'system_prompt')
        if prompt_type == 'romantic_prompt':
            current_system_prompt = romantic_prompt
        elif prompt_type == 'tech_prompt':
            current_system_prompt = tech_prompt
        elif prompt_type == 'creative_prompt':
            current_system_prompt = creative_prompt
    
    # Получаем историю из БД
    chat_history = db.get_history(chat_id)
    
    # Если история пуста, добавляем системный промпт
    if not chat_history:
        db.add_message(chat_id, "system", current_system_prompt)
        chat_history = [{"role": "system", "content": current_system_prompt}]
    else:
        # Проверяем, не изменился ли системный промпт
        if chat_history[0]['role'] == 'system':
            if context.user_data.get('admin_mode'):
                if chat_history[0]['content'] != current_system_prompt:
                    db.update_system_prompt(chat_id, current_system_prompt)
                    chat_history[0]['content'] = current_system_prompt
            else:
                if chat_history[0]['content'] != system_prompt:
                    db.update_system_prompt(chat_id, system_prompt)
                    chat_history[0]['content'] = system_prompt
    
    # Добавляем сообщение пользователя
    db.add_message(chat_id, "user", user_message)
    chat_history.append({"role": "user", "content": user_message})

    # Подготовка запроса
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://minisir-ai.onrender.com",
        "X-Title": "MiniSir AI Bot"
    }
    
    # Используем выбранную модель или модель по умолчанию
    current_model = context.user_data.get('model', DEFAULT_MODEL)
    
    try:
        # Определяем, какую модель использовать
        if current_model == "gemini-2.5-pro":
            # Используем Gemini API
            bot_response = await send_gemini_request(chat_history)
        else:
            # Используем OpenRouter API
            payload = {
                "model": current_model,
                "messages": chat_history,
                "temperature": 0.7
            }
            data = await send_api_request(payload, headers)
            bot_response = data["choices"][0]["message"]["content"]
        
        # Проверка на пустой ответ
        if not bot_response or not bot_response.strip():
            logger.warning("API вернул пустой ответ")
            await update.message.reply_text("🤔 Я не смог придумать ответ. Попробуй задать вопрос иначе!")
            return

        # Сохранение истории
        db.add_message(chat_id, "assistant", bot_response)

        # Удаляем индикатор "Думаю..." перед отправкой ответа
        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=thinking_msg.message_id
        )
        
        # Отправляем ответ пользователю
        await send_response(update, context, bot_response, current_model)

    except requests.exceptions.HTTPError as e:
        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=thinking_msg.message_id
        )
        error_msg = f"Ошибка API: {e.response.status_code}"
        logger.error(f"{error_msg}, Тело ответа: {e.response.text}")
        await update.message.reply_text(f"⚠️ Ошибка API: {e.response.status_code}")
    except Exception as e:
        # Редактируем индикатор в сообщение об ошибке
        await thinking_msg.edit_text(f"⚠️ Ошибка: {str(e)}")
        logger.error(f"Ошибка: {e}", exc_info=True)
    finally:
        # Всегда возвращаем клавиатуру
        if update.effective_chat:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Чем еще могу помочь?",
                reply_markup=admin_keyboard if context.user_data.get('admin_mode') else main_keyboard
            )
        context.user_data['processing'] = False

# Обработка пароля
async def password_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_input = update.message.text.strip()
    
    if user_input == ADMIN_PASSWORD:
        # Активация админ-режима
        context.user_data['admin_mode'] = True
        
        # Обновляем системный промпт в истории
        db.update_system_prompt(chat_id, admin_system_prompt)
        
        await update.message.reply_text(
            "🔓 Админ-режим активирован! Теперь я буду отвечать как твой парень для Алисы 😊",
            reply_markup=admin_keyboard
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ Неверный пароль! Попробуйте еще раз или выберите действие:",
            reply_markup=main_keyboard
        )
        return ConversationHandler.END

# Выбор промпта в админ-режиме
async def select_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_input = update.message.text.strip()
    
    if user_input in PROMPT_OPTIONS:
        prompt_type = PROMPT_OPTIONS[user_input]
        context.user_data['prompt_type'] = prompt_type
        
        # Обновляем системный промпт
        if prompt_type == 'system_prompt':
            db.update_system_prompt(chat_id, admin_system_prompt)
        elif prompt_type == 'romantic_prompt':
            db.update_system_prompt(chat_id, romantic_prompt)
        elif prompt_type == 'tech_prompt':
            db.update_system_prompt(chat_id, tech_prompt)
        elif prompt_type == 'creative_prompt':
            db.update_system_prompt(chat_id, creative_prompt)
        
        await update.message.reply_text(
            f"✅ Промпт успешно изменен на: {user_input}",
            reply_markup=admin_keyboard
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ Неизвестный тип промпта. Выберите из предложенных:",
            reply_markup=prompt_keyboard
        )
        return SELECTING_PROMPT

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    # Сброс истории
    db.reset_history(chat_id)
    
    # Сбрасываем админ-режим
    if 'admin_mode' in context.user_data:
        context.user_data['admin_mode'] = False
    
    # Сбрасываем выбранную модель
    if 'model' in context.user_data:
        del context.user_data['model']
    
    # Сбрасываем тип промпта
    if 'prompt_type' in context.user_data:
        del context.user_data['prompt_type']
    
    # Определяем текущую модель
    current_model = context.user_data.get('model', DEFAULT_MODEL)
    model_name = next((k for k, v in MODEL_OPTIONS.items() if v == current_model), current_model)
    
    welcome_text = (
        f"┏━━━━━━━✦❘༻༺❘✦━━━━━━━━┓\n"
        f"*Привет\\!* ✨\n"
        f"Чем сегодня займёмся? Помощь, творчество или просто поболтаем? 😊\n\n"
        f"🔧 _Текущая модель: {model_name}_\n"
        f"┗━━━━━━━✦❘༻༺❘✦━━━━━━━━┛"
    )
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=main_keyboard
    )
    return ConversationHandler.END

# Команда для выхода из админ-режима
async def exit_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if 'admin_mode' in context.user_data and context.user_data['admin_mode']:
        context.user_data['admin_mode'] = False
        # Обновляем системный промпт
        db.update_system_prompt(chat_id, system_prompt)
        await update.message.reply_text(
            "👋 Админ-режим деактивирован! Возвращаюсь в обычный режим.",
            reply_markup=main_keyboard
        )
    else:
        await update.message.reply_text(
            "ℹ️ Админ-режим не был активирован.",
            reply_markup=main_keyboard
        )

# Команда для смены промпта
async def change_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 Выберите тип промпта:",
        reply_markup=prompt_keyboard
    )
    return SELECTING_PROMPT

# Главная функция
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Запускаем Flask в отдельном потоке для пингов
    from threading import Thread
    Thread(target=lambda: flask_app.run(port=5000, host="0.0.0.0"), daemon=True).start()
    
    # Обработчики
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^👑 Админ$"), handle_message),
            CommandHandler("admin", lambda u, c: handle_message(u, c, "👑 Админ"))
        ],
        states={
            WAITING_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, password_handler)
            ],
            SELECTING_PROMPT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_prompt)
            ]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("exit_admin", exit_admin))
    app.add_handler(CommandHandler("change_prompt", change_prompt))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
