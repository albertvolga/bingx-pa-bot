import json
from google import genai
from config import GEMINI_API_KEY

def parse_user_intent(user_text: str) -> dict:
    if not GEMINI_API_KEY:
        return {"error": "GEMINI_API_KEY не установлен в .env"}

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        system_instruction = (
            "Ты — умный и дружелюбный ассистент трейдера по Price Action на бирже BingX.\n"
            "Твоя задача — проанализировать сообщение пользователя и вернуть ответ strictly в формате JSON.\n\n"
            "Формат JSON ответа:\n"
            "{\n"
            '  "type": "chat" | "alert",\n'
            '  "reply": "Твой живой человеческий ответ трейдеру (если type=chat или нужно прокомментировать)",\n'
            '  "symbol": "BTC" | "ETH" | ... (сокращенный тикер без USDT, только если type=alert),\n'
            '  "level_type": "exact" | "prev_d1_high" | "prev_d1_low" | null,\n'
            '  "target_price": float | null,\n'
            '  "is_multi": boolean\n'
            "}\n\n"
            "Правила распознавания типов запроса:\n"
            "1. Если пользователь просто общается, задает вопросы по рынку, трейдингу или жизнь — 'type': 'chat'. Помоги ему и ответь простым, понятным языком профессионального трейдера.\n"
            "2. Если пользователь хочет поставить алерт/напоминание на цену (например: 'поставь алерт на биткоин 65000', 'предупреди когда эфир пробьет хай вчерашнего дня') — 'type': 'alert'.\n"
            "   - Определи символ ('BTC', 'ETH', 'SOL' и т.д.).\n"
            "   - Определи точную цену 'target_price' ИЛИ 'level_type' ('prev_d1_high' для максимума вчерашнего дня, 'prev_d1_low' для минимума).\n"
            "   - 'is_multi': true, если пользователь просит многоразовый алерт, иначе false."
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_text,
            config={
                "system_instruction": system_instruction,
                "response_mime_type": "application/json",
            }
        )

        data = json.loads(response.text)
        return data

    except Exception as e:
        print(f"⚠️ Ошибка Gemini NLP: {e}")
        return {"error": str(e)}
