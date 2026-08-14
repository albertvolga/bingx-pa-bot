import requests

url = "https://open-api.bingx.com/openApi/swap/v3/quote/klines"
params = {
    "symbol": "BTC-USDT",
    "interval": "1h",
    "limit": 5
}

try:
    response = requests.get(url, params=params, timeout=5)
    data = response.json()
    print("Код ответа:", data.get("code"))
    print("Сообщение:", data.get("msg"))
    print("Получено свечей:", len(data.get("data", [])))
    if data.get("data"):
        print("Пример первой свечи:", data["data"][0])
except Exception as e:
    print("Ошибка запроса:", e)
