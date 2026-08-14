import requests
import json

from config import SYMBOL_MAP

def test():
    symbol = "BTC"
    interval = "1h"
    
    api_symbol = SYMBOL_MAP.get(symbol, symbol)
    api_interval = interval.lower()
    
    url = "https://open-api.bingx.com/openApi/swap/v3/quote/klines"
    params = {
        "symbol": api_symbol,
        "interval": api_interval,
        "limit": 30
    }
    
    print(f"Отправляем запрос:")
    print(f"URL: {url}")
    print(f"Params: {params}")
    
    res = requests.get(url, params=params, timeout=5)
    print(f"\nСтатус-код: {res.status_code}")
    print("Ответ API:")
    print(json.dumps(res.json(), indent=2, ensure_ascii=False))

if __name__ == "__main__":
    test()
