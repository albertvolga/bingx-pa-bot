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

async def get_ticker_price(symbol: str) -> float:
    """Получает текущую цену тикера на основе последней свечи."""
    try:
        klines = await fetch_klines(symbol, interval="1m", limit=1)
        if klines and len(klines) > 0:
            return float(klines[-1].get("close", 0))
    except Exception as e:
        logging.error(f"Ошибка при получении цены {symbol}: {e}")
    return 0.0

async def get_ticker_price(symbol: str) -> float:
    """Получает текущую цену тикера BingX."""
    try:
        clean_symbol = symbol.replace("-", "").upper()
        if clean_symbol.endswith("USDT"):
            clean_symbol = clean_symbol[:-4] + "-USDT"
        
        klines = await fetch_klines(clean_symbol, interval="1m", limit=1)
        if klines and len(klines) > 0:
            return float(klines[-1].get("close", 0))
    except Exception as e:
        logging.error(f"Ошибка при получении цены {symbol}: {e}")
    return 0.0
