import os
import json
import sqlite3
from datetime import datetime, timedelta
from groq import Groq

# Путь к базе данных контекста (сохраняется в корне проекта)
DB_PATH = "ai_memory.db"

# Системная инструкция для Groq Llama-3.3
SYSTEM_PROMPT = """
Ты — интеллектуальный ассистент трейдера и универсальный эксперт в составе Telegram-бота bingx-pa-bot.

ТВОИ РОЛИ И ПРАВИЛА ПОВЕДЕНИЯ:
1. АНАЛИЗ И ОБРАБОТКА АЛЕРТОВ (Приоритет №1):
   Если пользователь просит поставить, удалить, изменить ценовой или индикаторный алерт, либо узнать текущие алерты:
   - Парси запрос максимально гибко на естественном языке (например: "поставь уведомление на биток на 66000", "алерт на солану на хай вчерашнего дневного бара", "поставь алерты на максимум и минимум бара 4ч закрывшегося в 15:00 на каспе", "удали алерт по SOL", "удали все алерты", "когда возникнет фейки на солане на 1ч дай знать").
   - Извлекай комментарий пользователя, если он передал причину или цель установки алерта.
   - Верни СТРОГО СТРУКТУРИРОВАННЫЙ JSON (без разметки markdown, без кода ```json) в следующем формате:

   Для создания алерта:
   {
     "action": "CREATE_ALERT",
     "symbol": "BTC-USDT",
     "type": "PRICE" | "RELATIVE_LEVEL" | "INDICATOR_PAT",
     "condition": "ABOVE" | "BELOW" | "CROSS" | "PATTERN_APPEARED",
     "price": 66000.0 (или null),
     "relative_level": "HIGH_PREV_D1" | "LOW_PREV_D1" | "HIGH_BAR_H4" | "LOW_BAR_H4" | "CUSTOM" | null,
     "bar_time_ref": "15:00" (время конкретного бара, если указано, иначе null),
     "timeframe": "M15" | "H1" | "H4" | "D1" | null,
     "pattern_name": "FAKEY" | "PINBAR" | "ENGULFING" | "SQUAT" | "MFI" | null,
     "comment": "комментарий пользователя или null"
   }

   Для удаления одного или всех алертов:
   {
     "action": "DELETE_ALERT",
     "target": "ALL" | "SYMBOL",
     "symbol": "SOL-USDT" (если target="SYMBOL", иначе null)
   }

   Для просмотра алертов:
   {
     "action": "LIST_ALERTS"
   }

2. ЭКСПЕРТНЫЙ ДИАЛОГ И ОБЩЕНИЕ:
   - Если пользователь не дает жесткую команду на алерт, отвечай как эксперт в запрошенной или подходящей области (например, эксперт-трейдер Билл Вильямс, лингвист, программист, аналитик).
   - Отвечай глубоко, профессионально, кратко и по делу.
   
3. ЧЕСТНОСТЬ И УТОЧНЕНИЯ:
   - Если ты чего-то не понял, данные неполные или ты сомневаешься в тикере/цене — НЕ выдумывай значения! Ответь прямо или задай уточняющий вопрос.
"""

def init_db():
    """Инициализация БД для хранения диалога."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def clear_old_history(days: int = 60):
    """Удаление сообщений старше N дней (по умолчанию 60)."""
    cutoff_date = datetime.now() - timedelta(days=days)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "DELETE FROM chat_history WHERE created_at < ?",
            (cutoff_date.strftime("%Y-%m-%d %H:%M:%S"),)
        )
        conn.commit()

def save_message(user_id: int, role: str, content: str):
    """Сохранение сообщения в историю."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content)
        )
        conn.commit()

def get_user_history(user_id: int, days: int = 60) -> list:
    """Получение истории сообщений пользователя за последние 60 дней."""
    init_db()
    clear_old_history(days)
    
    cutoff_date = datetime.now() - timedelta(days=days)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT role, content FROM chat_history 
            WHERE user_id = ? AND created_at >= ? 
            ORDER BY id ASC
            """,
            (user_id, cutoff_date.strftime("%Y-%m-%d %H:%M:%S"))
        )
        rows = cursor.fetchall()
        
    return [{"role": r[0], "content": r[1]} for r in rows]

async def ask_groq_ai(user_id: int, user_message: str) -> dict:
    """
    Главная функция обработки запросов через Groq API.
    
    Возвращает словарь:
    {
       "type": "ALERT_ACTION" | "TEXT_RESPONSE",
       "data": dict | str
    }
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {
            "type": "TEXT_RESPONSE",
            "data": "⚠️ Ошибка: Переменная окружения GROQ_API_KEY не найдена в .env!"
        }

    client = Groq(api_key=api_key)

    # 1. Загружаем контекст пользователя за 60 дней
    history = get_user_history(user_id, days=60)

    # 2. Составляем итоговый массив сообщений
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    try:
        # 3. Запрос к Groq Llama-3.3-70b
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.2,
            max_tokens=1000
        )
        
        raw_response = completion.choices[0].message.content.strip()

        # 4. Проверяем, вернул ли ИИ JSON-команду для алертов
        if raw_response.startswith("{") and raw_response.endswith("}"):
            try:
                alert_data = json.loads(raw_response)
                save_message(user_id, "user", user_message)
                save_message(user_id, "assistant", f"[Выполнена команда алерта: {alert_data.get('action')}]")
                return {
                    "type": "ALERT_ACTION",
                    "data": alert_data
                }
            except json.JSONDecodeError:
                pass

        # 5. Если это текстовый экспертный ответ
        save_message(user_id, "user", user_message)
        save_message(user_id, "assistant", raw_response)

        return {
            "type": "TEXT_RESPONSE",
            "data": raw_response
        }

    except Exception as e:
        return {
            "type": "TEXT_RESPONSE",
            "data": f"❌ Ошибка обращения к Groq API: {str(e)}"
        }
