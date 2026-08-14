import json
import os
from groq import AsyncGroq

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

SYSTEM_PROMPT = """
Ты — торговый ассистент по Price Action для криптовалютного бота BingX.
Твоя задача — строго анализировать текст пользователя и выявлять интенты для создания ценовых алертов.

КРИТИЧЕСКИЕ ПРАВИЛА ПО СИМВОЛУ (SYMBOL):
1. Если пользователь ЯВНО указал монету (например: Эфир, ETH, Bitcoin, BTC, Solana, SOL, Kaspa, KAS и т.д.), укажи её в поле "symbol" (например, "ETH").
2. Если пользователь НЕ указал монету в тексте сообщения, значение "symbol" ОБЯЗАТЕЛЬНО должно быть "NONE" или null!
   КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО подставлять BTC, KAS или любую другую монету по умолчанию, если о ней не написано в запросе!

Формат ответа строго JSON (без лишнего текста вокруг):
{
  "type": "alert_intent",
  "data": [
    {
      "symbol": "ETH" | "BTC" | "SOL" | "NONE",
      "target_price": float или null,
      "target_level": "high" | "low" | "close" | null,
      "comment": "строка с кратким объяснением"
    }
  ]
}

Если сообщение пользователя — это обычный вопрос или приветствие (не интент алерта), верни:
{
  "type": "text",
  "content": "Твой текстовый ответ пользователю..."
}
"""

async def process_ai_message(user_text: str):
    if not client:
        return {"type": "text", "content": "⚠️ GROQ_API_KEY не установлен."}

    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        content = response.choices[0].message.content
        data = json.loads(content)
        return data
    except Exception as e:
        print(f"Groq AI Error: {e}")
        return {"type": "text", "content": f"⚠️ Ошибка обработчика AI: {e}"}
