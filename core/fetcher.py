import logging
from core.bingx.candles import fetch_bingx_candles, get_ticker_price

SCAN_SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "DOT-USDT", "PAXG-USDT", "DOGE-USDT", "ADA-USDT"]

async def fetch_klines(symbol: str, interval: str = "1h", limit: int = 100, end_time: int = None):
    try:
        klines = await fetch_bingx_candles(symbol, timeframe=interval, limit=limit, interval=interval, end_time=end_time)
        return klines
    except Exception as e:
        logging.error(f"Ошибка при получении свечей {symbol} ({interval}): {e}")
        return []

async def get_all_usdt_pairs():
    return SCAN_SYMBOLS
