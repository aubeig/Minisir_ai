# config.py
import os
from telegram import ReplyKeyboardMarkup

# --- КЛЮЧИ И НАСТРОЙКИ ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "illovyly")
ADMIN_IDS = [int(admin_id) for admin_id in os.getenv("ADMIN_IDS", "").split(",") if admin_id]

MAX_HISTORY_LENGTH = 10

# --- АНИМАЦИЯ ---
THINKING_ANIMATION = ["Думаю 🤔 \. \. \.", "Думаю 🤔 \.\. \.", "Думаю 🤔 \.\.\.", "Думаю 🤔 \. \.\."]
SEARCHING_ANIMATION = ["Ищу 🔎 \. \. \.", "Ищу 🔎 \.\. \.", "Ищу 🔎 \.\.\.", "Ищу 🔎 \. \.\."]

# --- ВАШИ ОРИГИНАЛЬНЫЕ МОДЕЛИ ---
DEFAULT_MODEL = "qwen/qwen3-235b-a22b:free"
MODEL_OPTIONS = {
    "Мини-Сырок Lite": "deepseek/deepseek-r1:free",
    "Мини-Сырок V1": "qwen/qwen3-235b-a22b:free",
    "Мини-Сырок Max": "gemini-2.5-pro",
}

# --- ВАШИ ОРИГИНАЛЬНЫЕ КЛАВИАТУРЫ ---
main_keyboard = ReplyKeyboardMarkup([["✍️ Начать", "👑 Админ", "🧩 Тех.поддержка"], ["🧠 Модели", "🔍 Поиск в Google"]], resize_keyboard=True)
model_keyboard = ReplyKeyboardMarkup([["Мини-Сырок Lite", "Мини-Сырок V1"], ["Мини-Сырок Max", "🔙 Назад"]], resize_keyboard=True)
admin_keyboard = ReplyKeyboardMarkup([["🔓 Выйти из админа", "🔄 Сменить промпт"], ["🎨 Создать изображение", "🔙 Назад"]], resize_keyboard=True)

# --- СОСТОЯНИЯ ДИАЛОГА ---
SELECTING_ACTION, WAITING_PASSWORD, ADMIN_MODE, WAITING_SEARCH_QUERY = range(4)

# --- ВАШИ ПРОМТЫ ---
# Вставьте сюда ваши полные промты
system_prompt = """...""" # ВАШ ОБЫЧНЫЙ ПРОМПТ
admin_system_prompt = """...""" # ВАШ АДМИНСКИЙ ПРОМПТ
