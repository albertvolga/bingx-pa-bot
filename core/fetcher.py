import logging
from core.bingx.candles import fetch_bingx_candles # Уточненный импорт

async def fetch_klines(symbol: str, interval: str = "1h", limit: int = 100, end_time_ms: int = None):
    """
    Асинхронная обертка над получением свечей с обязательным await
    и поддержкой запроса исторических данных до определенного времени (end_time_ms).
    """
    try:
        klines = await fetch_bingx_candles(symbol, timeframe=interval, limit=limit, interval=interval, end_time_ms=end_time_ms)
        return klines
    except Exception as e:
        logging.error(f"Ошибка при получении свечей {symbol} ({interval}, end_time_ms={end_time_ms}): {e}")
        return []
