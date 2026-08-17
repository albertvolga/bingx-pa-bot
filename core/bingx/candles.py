import aiohttp
import asyncio

BINGX_BASE_URL = "https://open-api.bingx.com"

async def fetch_bingx_candles(symbol: str, timeframe: str = "1h", limit: int = 10, interval: str = None):
    """
    Получение свечей BingX (поддерживает аргументы timeframe и interval)
    """
    tf = interval or timeframe or "1h"
    tf_map = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w"
    }
    tf_val = tf_map.get(str(tf).lower(), "1h")
    
    sym = symbol.upper()
    if not sym.endswith("-USDT"):
        sym = f"{sym.replace("-USDT", "").replace("USDT", "")}-USDT"

    # Пробуем сначала Swap API, при ошибке контракта — Spot API
    urls = [
        f"{BINGX_BASE_URL}/openApi/swap/v2/quote/klines",
        f"{BINGX_BASE_URL}/openApi/spot/v1/market/kline"
    ]

    for url in urls:
        params = {
            "symbol": sym,
            "interval": tf_val,
            "limit": limit
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as resp:
                    data = await resp.json()
                    if data.get("code") == 0 and "data" in data:
                        raw_klines = data["data"]
                        # Приводим к единому формату time/high/low/close
                        klines = []
                        for k in raw_klines:
                            klines.append({
                                "time": k.get("time") or k.get("time"),
                                "high": float(k.get("high")),
                                "low": float(k.get("low")),
                                "close": float(k.get("close")),
                                "open": float(k.get("open", 0))
                            })
                        return sorted(klines, key=lambda x: x["time"])
        except Exception:
            continue

    print(f"⚠️ BingX API: Не удалось загрузить свечи для {sym}")
    return []

async def fetch_klines(symbol: str, timeframe: str = "1h", limit: int = 10, interval: str = None):
    return await fetch_bingx_candles(symbol, timeframe=timeframe, limit=limit, interval=interval)

async def get_ticker_price(symbol: str) -> float:
    sym = symbol.upper()
    if not sym.endswith("-USDT"):
        sym = f"{sym.replace("-USDT", "").replace("USDT", "")}-USDT"

    urls = [
        (f"{BINGX_BASE_URL}/openApi/swap/v2/quote/price", {"symbol": sym}),
        (f"{BINGX_BASE_URL}/openApi/spot/v1/ticker/24hr", {"symbol": sym})
    ]

    for url, params in urls:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as resp:
                    data = await resp.json()
                    if data.get("code") == 0 and "data" in data:
                        res = data["data"]
                        if isinstance(res, list) and len(res) > 0:
                            return float(res[0].get("lastPrice", 0))
                        elif isinstance(res, dict):
                            return float(res.get("price") or res.get("lastPrice") or 0)
        except Exception:
            continue
    return 0.0
