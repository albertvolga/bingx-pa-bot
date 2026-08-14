import logging
from core.bingx.candles import fetch_bingx_candles

async def fetch_klines(symbol: str, interval: str, limit: int = 30):
    """
    Адаптер для получения свечей через родную функцию fetch_bingx_candles
    """
    try:
        df = fetch_bingx_candles(symbol=symbol, interval=interval, limit=limit)
        return df
    except Exception as e:
        logging.error(f"Ошибка при получении свечей {symbol} ({interval}): {e}")
        return None

async def get_all_usdt_pairs():
    return ["BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "LTC-USDT", "DOT-USDT", "DOGE-USDT", "ADA-USDT", "ATOM-USDT"]
