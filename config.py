import os
from datetime import timezone, timedelta
from dotenv import load_dotenv

# Загружаем переменные из файла .env
load_dotenv()

# Часовой пояс Москва (UTC+3)
MSK_TZ = timezone(timedelta(hours=3))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

SYMBOL_MAP = {
    "BTC": "BTC-USDT",
    "ETH": "ETH-USDT",
    "SOL": "SOL-USDT",
    "KAS": "KAS-USDT",
    "LTC": "LTC-USDT",
    "DOT": "DOT-USDT",
    "DOGE": "DOGE-USDT",
    "ATOM": "ATOM-USDT",
    "ADA": "ADA-USDT",
    "XRP": "XRP-USDT",
    "XAU": "XAU-USDT",
    "XAG": "XAG-USDT"
}
