# utils.py
import re
import asyncio
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest
import logging
from datetime import datetime
import markdown
import httpx
import google.generativeai as genai
from config import OPENROUTER_API_KEY, GEMINI_API_KEY, GOOGLE_API_KEY, GOOGLE_CSE_ID

# Инициализация моделей
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel("gemini-1.5-pro-latest")
else:
    gemini_model = None

http_client = httpx.AsyncClient(timeout=120.0)
logger = logging.getLogger(__name__)

def escape_markdown_v2(text: str) -> str:
    escape_chars = r'_*[]()~`>#+-={}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

async def show_animation(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, animation_frames: list):
    context.user_data['processing'] = True
    i = 0
    while context.user_data.get('processing', False):
        try:
            await context.bot.edit_message_text(
                text=animation_frames[i % len(animation_frames)],
                chat_id=chat_id,
                message_id=message_id,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            i += 1
            await asyncio.sleep(1)
        except BadRequest:
            await asyncio.sleep(1)
        except Exception:
            break

def parse_ai_response(full_response: str) -> (str, str):
    think_match = re.search(r"<think>(.*?)</think>", full_response, re.DOTALL)
    if think_match:
        thoughts = think_match.group(1).strip()
        answer = re.sub(r"<think>.*?</think>", "", full_response, flags=re.DOTALL).strip()
        return thoughts, answer
    return "Мысли не были сгенерированы.", full_response

def generate_admin_html(query: str, thoughts: str, answer: str) -> str:
    try:
        with open("templates/log_template.html", "r", encoding="utf-8") as f_template, \
             open("templates/styles.css", "r", encoding="utf-8") as f_css:
            template_str, css_str = f_template.read(), f_css.read()

        html_with_css = template_str.replace('<link rel="stylesheet" href="styles.css">', f'<style>{css_str}</style>')
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        answer_html = markdown.markdown(answer)

        final_html = html_with_css.replace("{{timestamp}}", timestamp)
        final_html = final_html.replace("{{query}}", query)
        final_html = final_html.replace("{{thoughts}}", thoughts)
        final_html = final_html.replace("{{answer_html}}", answer_html)
        return final_html
    except Exception as e:
        logger.error(f"Ошибка генерации HTML: {e}")
        return f"<h1>Ошибка</h1><p>Не удалось сгенерировать отчет: {e}</p>"

async def get_ai_response(model_name: str, chat_history: list) -> str:
    if model_name == "gemini-2.5-pro":
        if not gemini_model: raise ValueError("Gemini API Key не настроен.")
        response = await gemini_model.generate_content_async(chat_history)
        return response.text
    else:
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
        payload = {"model": model_name, "messages": chat_history}
        api_response = await http_client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        api_response.raise_for_status()
        return api_response.json()["choices"][0]["message"]["content"]

async def google_search_and_summarize(query: str) -> str:
    if not (GOOGLE_API_KEY and GOOGLE_CSE_ID):
        return "Функция поиска не настроена."
    
    params = {"key": GOOGLE_API_KEY, "cx": GOOGLE_CSE_ID, "q": query, "num": 3}
    try:
        response = await http_client.get("https://www.googleapis.com/customsearch/v1", params=params)
        response.raise_for_status()
        search_results = response.json().get('items', [])
        
        if not search_results:
            return "Не удалось найти информацию по вашему запросу."
            
        context_for_ai = f"Пользователь ищет информацию по запросу: '{query}'.\n\nВот результаты поиска:\n"
        for item in search_results:
            context_for_ai += f"**Заголовок:** {item.get('title', '')}\n**Фрагмент:** {item.get('snippet', '')}\n---\n"
        
        summary_prompt = "Сделай краткую, но информативную выжимку на основе предоставленных результатов поиска. Ответь на запрос пользователя четко и по делу, как будто ты сам это знаешь. Не упоминай, что ты используешь результаты поиска, просто дай связный ответ."
        
        if not gemini_model: raise ValueError("Gemini API Key не настроен для суммаризации.")
        summary_response = await gemini_model.generate_content_async(f"{context_for_ai}\n\n**Задание:** {summary_prompt}")
        return summary_response.text

    except httpx.HTTPError as e:
        logger.error(f"Ошибка поиска Google: {e}")
        return f"Произошла ошибка при поиске: {e}"
