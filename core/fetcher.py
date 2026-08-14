import logging
from core.bingx import fetch_bingx_candles

async def fetch_klines(symbol: str, interval: str = "1h", limit: int = 100):
    """
    Асинхронная обертка над получение свечей с обязательным await
    """
    try:
        # Важно: обязательно делаем await!
        klines = await fetch_bingx_candles(symbol, timeframe=interval, limit=limit, interval=interval)
        return klines
    except Exception as e:
        logging.error(f"Ошибка при получении свечей {symbol} ({interval}): {e}")
        return []
