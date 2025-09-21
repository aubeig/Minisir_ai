# handlers.py
import logging
import asyncio
from telegram import Update, ReplyKeyboardRemove, InputFile
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode, ChatAction
from io import BytesIO

from config import *
from database import ChatHistoryDB
from utils import *

logger = logging.getLogger(__name__)
db = ChatHistoryDB()

# --- ОСНОВНЫЕ КОМАНДЫ И ДЕЙСТВИЯ ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Привет\! Я Мини\-Сырок\. Готов помочь с кодом, идеями или просто пообщаться\.",
        reply_markup=main_keyboard, parse_mode=ParseMode.MARKDOWN_V2
    )
    return SELECTING_ACTION

async def tech_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠️ Свяжитесь с техподдержкой:\nhttps://t\.me/Aubeig",
        reply_markup=main_keyboard, parse_mode=ParseMode.MARKDOWN_V2
    )

async def show_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧠 *Выберите модель:*\n\n• Мини\-Сырок Lite — быстрая и легкая\n• Мини\-Сырок V1 — баланс скорости и качества\n• Мини\-Сырок Max — максимальная мощность",
        parse_mode=ParseMode.MARKDOWN_V2, reply_markup=model_keyboard
    )

async def set_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text in MODEL_OPTIONS:
        context.user_data['model'] = MODEL_OPTIONS[text]
        await update.message.reply_text(
            f"✅ Модель изменена на *{escape_markdown_v2(text)}*",
            parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_keyboard
        )

# --- ЛОГИКА АДМИН-ПАНЕЛИ ---

async def admin_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("🔒 Введите пароль:", reply_markup=ReplyKeyboardRemove())
    return WAITING_PASSWORD

async def handle_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == ADMIN_PASSWORD:
        context.user_data['admin_mode'] = True
        await update.message.reply_text("🔓 Админ\-режим активирован\.", reply_markup=admin_keyboard, parse_mode=ParseMode.MARKDOWN_V2)
        return ADMIN_MODE
    else:
        await update.message.reply_text("❌ Неверный пароль\.", reply_markup=main_keyboard, parse_mode=ParseMode.MARKDOWN_V2)
        return SELECTING_ACTION

async def exit_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop('admin_mode', None)
    await update.message.reply_text("✅ Админ\-режим выключен\.", reply_markup=main_keyboard, parse_mode=ParseMode.MARKDOWN_V2)
    return SELECTING_ACTION

# --- ГЛАВНЫЙ ОБРАБОТЧИК ---

async def main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Центральный обработчик, который вызывает другие в зависимости от типа сообщения."""
    if update.message.text:
        await handle_text(update, context)
    # Добавьте здесь обработчики для других типов контента, если нужно
    # elif update.message.voice:
    #     await handle_voice(update, context)
    # ...и так далее

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_message = update.message.text

    thinking_msg = await update.message.reply_text(THINKING_ANIMATION[0], parse_mode=ParseMode.MARKDOWN_V2)
    animation_task = asyncio.create_task(show_animation(context, chat_id, thinking_msg.message_id, THINKING_ANIMATION))
    
    final_text = ""
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        
        is_admin = user_id in ADMIN_IDS and context.user_data.get('admin_mode', False)
        current_prompt = admin_system_prompt if is_admin else system_prompt
        
        chat_history = db.get_history(chat_id)
        if not chat_history or chat_history[0].get('content') != current_prompt:
            db.update_system_prompt(chat_id, current_prompt)
            chat_history = [{"role": "system", "content": current_prompt}]

        db.add_message(chat_id, "user", user_message)
        chat_history.append({"role": "user", "content": user_message})
        
        current_model_name = context.user_data.get('model', DEFAULT_MODEL)
        
        raw_response = await get_ai_response(current_model_name, chat_history)
        
        if not raw_response.strip():
            raise ValueError("API вернул пустой ответ.")
        
        thoughts, answer = parse_ai_response(raw_response)
        
        db.add_message(chat_id, "assistant", answer)
        final_text = escape_markdown_v2(answer)

        # Отправка HTML-отчета админу
        if user_id in ADMIN_IDS:
            html_report = generate_admin_html(user_message, thoughts, answer)
            report_file = BytesIO(html_report.encode('utf-8'))
            await context.bot.send_document(
                chat_id=user_id,
                document=InputFile(report_file, filename=f"log_{update.message.message_id}.html"),
                caption=f"Отчет для запроса: `{user_message[:50]}...`"
            )

    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}", exc_info=True)
        final_text = f"Произошла ошибка: {escape_markdown_v2(str(e))}"
    finally:
        context.user_data['processing'] = False
        await asyncio.sleep(0.1)
        await thinking_msg.edit_text(final_text, parse_mode=ParseMode.MARKDOWN_V2)

# --- Обработчик поиска ---
async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.message.text
    thinking_msg = await update.message.reply_text(SEARCHING_ANIMATION[0], parse_mode=ParseMode.MARKDOWN_V2)
    animation_task = asyncio.create_task(show_animation(context, thinking_msg.chat_id, thinking_msg.message_id, SEARCHING_ANIMATION))
    
    final_text = ""
    try:
        summary = await google_search_and_summarize(query)
        final_text = escape_markdown_v2(summary)
    except Exception as e:
        logger.error(f"Ошибка при поиске и суммаризации: {e}")
        final_text = "⚠️ Произошла ошибка при обработке вашего поискового запроса\."
    finally:
        context.user_data['processing'] = False
        await asyncio.sleep(0.1)
        await thinking_msg.edit_text(final_text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_keyboard)
    
    return SELECTING_ACTION
