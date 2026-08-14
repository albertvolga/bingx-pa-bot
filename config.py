import os
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BINGX_API_KEY = os.getenv("BINGX_API_KEY", "")
BINGX_SECRET_KEY = os.getenv("BINGX_SECRET_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Маппинг символов для BingX
SYMBOL_MAP = {
    "BTC": "BTC-USDT",
    "ETH": "ETH-USDT",
    "SOL": "SOL-USDT",
    "XRP": "XRP-USDT",
    "BNB": "BNB-USDT",
    "DOGE": "DOGE-USDT",
    "ADA": "ADA-USDT",
    "AVAX": "AVAX-USDT",
    "DOT": "DOT-USDT",
    "LINK": "LINK-USDT",
    "GOLD": "PAXG-USDT"
}

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Ошибка: TELEGRAM_BOT_TOKEN не найден в .env файле!")
