import aiohttp
import asyncio
import logging # Added import

BINGX_BASE_URL = "https://open-api.bingx.com"

async def fetch_bingx_candles(symbol: str, timeframe: str = "1h", limit: int = 10, interval: str = None, end_time_ms: int = None):
    """
    Получение свечей BingX (поддерживает аргументы timeframe, interval и end_time_ms для исторических данных)
    :param symbol: Торговый символ (например, "BTC-USDT")
    :param timeframe: Таймфрейм (например, "1h", "4h", "1d")
    :param limit: Количество свечей для получения
    :param interval: Альтернативное имя для timeframe (если используется)
    :param end_time_ms: Timestamp в миллисекундах для конечной точки (исторические данные до этого времени)
    """
    tf = interval or timeframe or "1h"
    tf_map = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w"
    }
    tf_val = tf_map.get(str(tf).lower(), "1h")
    
    sym = symbol.upper()
    if not sym.endswith("-USDT"):
        sym = f"{sym}-USDT"

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
        if end_time_ms:
            params["endTime"] = end_time_ms # Добавляем параметр endTime
            # Если указан endTime, то API возвращает свечи ЗАКОНЧИВШИЕСЯ ДО этого времени.
            # Если мы хотим свечи "до" 11:00 UTC, то последняя будет закрыта в 10:00 UTC.
            # Поэтому для limit=X, мы получим X свечей, последняя из которых закрыта до endTime.

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
                        # API может вернуть не до конца отсортированные данные, сортируем по времени открытия
                        return sorted(klines, key=lambda x: x["time"])
        except Exception as e:
            logging.warning(f"BingX API: Ошибка при получении свечей для {sym} с {url}: {e}")
            continue

    logging.warning(f"BingX API: Не удалось загрузить свечи для {sym} (TF: {tf_val}, Limit: {limit}, EndTime: {end_time_ms})")
    return []

async def fetch_klines(symbol: str, timeframe: str = "1h", limit: int = 10, interval: str = None, end_time_ms: int = None):
    # Обертка для fetch_bingx_candles с поддержкой end_time_ms
    return await fetch_bingx_candles(symbol, timeframe=timeframe, limit=limit, interval=interval, end_time_ms=end_time_ms)

async def get_ticker_price(symbol: str) -> float:
    sym = symbol.upper()
    if not sym.endswith("-USDT"):
        sym = f"{sym}-USDT"

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

async def get_all_usdt_pairs() -> list:
    """
    Получение всех USDT пар со спота и фьючерсов BingX.
    """
    all_pairs = set()
    urls = [
        f"{BINGX_BASE_URL}/openApi/swap/v2/quote/contracts", # Фьючерсы
        f"{BINGX_BASE_URL}/openApi/spot/v1/market/symbols" # Спот (обновленный эндпоинт для списка символов)
    ]

    for url in urls:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    data = await resp.json()
                    if data.get("code") == 0 and "data" in data:
                        if "contracts" in url: # Swap
                            for item in data["data"]:
                                # Только фьючерсные контракты с USDT
                                if item.get("currency") == "USDT" and item.get("status") == "TRADING" and item.get("symbol"):
                                    all_pairs.add(item["symbol"])
                        elif "symbols" in url: # Spot
                            for item in data["data"]:
                                # Только спотовые пары с USDT
                                if item.get("quoteAsset") == "USDT" and item.get("status") == "TRADING" and item.get("symbol"):
                                    all_pairs.add(item["symbol"])
        except Exception as e:
            logging.warning(f"BingX API: Ошибка при получении пар с {url}: {e}")
            continue
            
    # Приводим к единому формату SYMBOL-USDT
    formatted_pairs = []
    for pair in all_pairs:
        if "-USDT" in pair:
            formatted_pairs.append(pair)
        elif "USDT" in pair: # Например, BTCUSDT -> BTC-USDT
            # Заменяем только если USDT находится в конце, чтобы не затронуть токены типа "USDTP"
            formatted_pairs.append(f"{pair.removesuffix('USDT')}-USDT")

    return sorted(list(set(formatted_pairs)))
