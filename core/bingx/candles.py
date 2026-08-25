import logging
import pandas as pd
import aiohttp

TARGET_SYMBOLS = [
    "BTC-USDT",
    "ETH-USDT",
    "SOL-USDT",
    "KAS-USDT",
    "LTC-USDT",
    "DOT-USDT",
    "DOGE-USDT",
    "ATOM-USDT",
    "ADA-USDT",
    "XRP-USDT",
    "XAU-USDT",
    "XAG-USDT"
]

async def fetch_bingx_candles(symbol: str, timeframe: str = "1h", limit: int = 500, interval: str = None, **kwargs) -> pd.DataFrame:
    tf = interval if interval is not None else timeframe
    
    sym = symbol.upper()
    if not sym.endswith("-USDT"):
        sym = f"{sym}-USDT"
    
    url = "https://open-api.bingx.com/openApi/swap/v2/quote/klines"
    params = {
        "symbol": sym,
        "interval": tf,
        "limit": limit
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("code") == 0 and "data" in data:
                        raw_candles = data["data"]
                        df = pd.DataFrame(raw_candles)
                        if not df.empty:
                            df = df.rename(columns={
                                "time": "timestamp",
                                "open": "open",
                                "high": "high",
                                "low": "low",
                                "close": "close",
                                "volume": "volume"
                            })
                            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                            for col in ["open", "high", "low", "close", "volume"]:
                                df[col] = df[col].astype(float)
                            return df
    except Exception as e:
        logging.error(f"Ошибка при запросе свечей {sym}: {e}")
    
    return pd.DataFrame()

fetch_klines = fetch_bingx_candles

async def get_ticker_price(symbol: str) -> float:
    df = await fetch_bingx_candles(symbol, timeframe="1m", limit=1)
    if not df.empty:
        return float(df["close"].iloc[-1])
    return 0.0

async def get_all_usdt_pairs():
    """Возвращает строго ограниченный список активов для сканирования."""
    return TARGET_SYMBOLS
