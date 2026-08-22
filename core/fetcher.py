import logging
from core.bingx.candles import fetch_bingx_candles

async def fetch_klines(symbol: str, interval: str = "1h", limit: int = 100, end_time_ms: int = None):
    """
    Асинхронная обертка над получением свечей с поддержкой end_time_ms.
    """
    try:
        klines = await fetch_bingx_candles(symbol, timeframe=interval, limit=limit, interval=interval, end_time_ms=end_time_ms)
        return klines
    except Exception as e:
        logging.error(f"Ошибка при получении свечей {symbol} ({interval}, end_time_ms={end_time_ms}): {e}")
        return None


async def get_ticker_price(symbol: str) -> float:
    """Получает текущую цену тикера BingX."""
    try:
        clean_symbol = symbol.replace("-", "").upper()
        if not clean_symbol.endswith("-USDT"):
            clean_symbol = f"{clean_symbol.replace('USDT', '')}-USDT"
        
        klines = await fetch_klines(clean_symbol, interval="1m", limit=1)
        if klines is not None and not klines.empty:
            return float(klines.iloc[-1]["close"])
    except Exception as e:
        logging.error(f"Ошибка при получении цены {symbol}: {e}")
    return 0.0
