import os
import json
import re
from google import genai

# Берем API-ключ из окружения или из config
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GROQ_API_KEY")
if not GEMINI_API_KEY:
    try:
        import config
        GEMINI_API_KEY = getattr(config, "GEMINI_API_KEY", getattr(config, "GROQ_API_KEY", None))
    except Exception:
        pass

COIN_MAP = {
    "каспу": "KAS", "каспа": "KAS", "каспе": "KAS", "kaspa": "KAS", "kas": "KAS",
    "биток": "BTC", "биткоин": "BTC", "биткоина": "BTC", "биткоине": "BTC", "btc": "BTC", "bitcoin": "BTC",
    "эфир": "ETH", "эфириум": "ETH", "эфира": "ETH", "eth": "ETH", "ethereum": "ETH",
    "соляну": "SOL", "соляна": "SOL", "солану": "SOL", "солана": "SOL", "sol": "SOL", "solana": "SOL",
    "рипл": "XRP", "риппл": "XRP", "xrp": "XRP",
    "доги": "DOGE", "догкоин": "DOGE", "doge": "DOGE",
    "тон": "TON", "тонкоин": "TON", "ton": "TON"
}

def normalize_timeframe(text: str) -> str:
    text_lower = text.lower()
    if re.search(r'4\s*(?:х|х-часовой|-часовый|-часовой|часа|часовую|h|ч)', text_lower):
        return "4h"
    if re.search(r'1\s*(?:х|х-часовой|-часовый|-часовой|час|часовую|h|ч)', text_lower):
        return "1h"
    if re.search(r'15\s*(?:минут|мин|m)', text_lower):
        return "15m"
    if re.search(r'5\s*(?:минут|мин|m)', text_lower):
        return "5m"
    if re.search(r'1\s*(?:день|дневка|дневной|дневную|d|д)', text_lower):
        return "1d"
    return "1h"

def parse_user_intent(user_text: str) -> dict:
    user_text_lower = user_text.lower()
    detected_symbol = None
    for word, symbol in COIN_MAP.items():
        if re.search(r'\b' + re.escape(word) + r'\b', user_text_lower):
            detected_symbol = symbol
            break

    timeframe = normalize_timeframe(user_text)

    # Определяем тип уровня по тексту (лоу, хай, поу)
    level_type = "exact"
    if "лоу" in user_text_lower or "low" in user_text_lower or "минимум" in user_text_lower:
        level_type = "prev_candle_low"
    elif "хай" in user_text_lower or "high" in user_text_lower or "максимум" in user_text_lower:
        level_type = "prev_candle_high"
    elif "поу" in user_text_lower or "pou" in user_text_lower or "закрытие" in user_text_lower:
        level_type = "prev_candle_close"

    # Базовая структура запроса
    parsed = {
        "type": "alert" if ("алерт" in user_text_lower or "поставь" in user_text_lower or "установи" in user_text_lower) else "chat",
        "symbol": detected_symbol or "BTC",
        "timeframe": timeframe,
        "level_type": level_type,
        "reply": "Обрабатываю ваш запрос..."
    }

    if GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            system_instruction = (
                "Ты — умный ассистент трейдера по Price Action.\n"
                "Верни ответ STRICTLY в JSON:\n"
                "{\n"
                '  "type": "chat" | "alert",\n'
                '  "symbol": "KAS" | "BTC" | "ETH" | ...,\n'
                '  "timeframe": "4h" | "1h" | "15m" | "1d",\n'
                '  "level_type": "prev_candle_low" | "prev_candle_high" | "prev_candle_close" | "exact",\n'
                '  "reply": "текст ответа"\n'
                "}"
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
            if isinstance(data, dict):
                parsed.update(data)
        except Exception as e:
            print(f"⚠️ Warning Gemini NLP: {e}")

    # Локальные правила в приоритете для русских названий и таймфреймов
    if detected_symbol:
        parsed["symbol"] = detected_symbol
    if timeframe:
        parsed["timeframe"] = timeframe
    if level_type != "exact":
        parsed["level_type"] = level_type

    return parsed
