import requests
import pandas as pd
from datetime import datetime
import pytz
from config import SYMBOL_MAP

MSK_TZ = pytz.timezone('Europe/Moscow')

TF_SECONDS = {
    '1m': 60,
    '3m': 180,
    '5m': 300,
    '15m': 900,
    '30m': 1800,
    '1h': 3600,
    '2h': 7200,
    '4h': 14400,
    '6h': 21600,
    '12h': 43200,
    '1d': 86400
}

def fetch_bingx_candles(symbol: str, interval: str, limit: int = 30, end_time: int = None) -> pd.DataFrame:
    """
    Загружает исторические свечи с BingX API.
    """
    # Преобразуем BTC -> BTC-USDT, если передан короткий тикер
    api_symbol = SYMBOL_MAP.get(symbol, symbol)
    api_interval = interval.lower() # Убеждаемся в нижнем регистре (1h, 4h, 1d)

    url = "https://open-api.bingx.com/openApi/swap/v3/quote/klines"
    
    params = {
        "symbol": api_symbol,
        "interval": api_interval,
        "limit": limit
    }
    
    if end_time is not None:
        tf_sec = TF_SECONDS.get(api_interval, 3600)
        start_time = end_time - (limit * tf_sec * 1000)
        params["startTime"] = start_time
        params["endTime"] = end_time

    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        
        if data.get("code") != 0 or not data.get("data"):
            return pd.DataFrame()

        klines = data["data"]
        df = pd.DataFrame(klines)
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = df[col].astype(float)
            
        df['timestamp'] = df['time'].astype(int) // 1000
        df['datetime_msk'] = df['timestamp'].apply(lambda x: datetime.fromtimestamp(x, MSK_TZ))
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        return df
    except Exception as e:
        print(f"⚠️ Ошибка сети или таймаут BingX ({symbol} {interval}): {e}")
        return pd.DataFrame()
