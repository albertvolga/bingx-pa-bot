import requests

url = "https://open-api.bingx.com/openApi/swap/v3/quote/klines"
params = {
    "symbol": "BTC-USDT",
    "interval": "1h",
    "limit": 5
}

response = requests.get(url, params=params, timeout=5)
print("Статус ответа:", response.status_code)
print("Тело ответа BingX:")
print(response.json())
