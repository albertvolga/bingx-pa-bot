import urllib.request
import urllib.parse
import subprocess
import time
import json
import os

# Читаем конфигурацию
from config import BOT_TOKEN, USER_ID

SERVICE_NAME = "bingx-bot"

def send_telegram_alert(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = urllib.parse.urlencode({
            "chat_id": USER_ID,
            "text": message,
            "parse_mode": "HTML"
        }).encode('utf-8')
        req = urllib.request.Request(url, data=payload)
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"Ошибка отправки аларта через Watchdog: {e}")

def is_service_active():
    try:
        res = subprocess.run(["systemctl", "is-active", SERVICE_NAME], capture_output=True, text=True)
        return res.stdout.strip() == "active"
    except Exception:
        return False

if __name__ == "__main__":
    if not is_service_active():
        # Пробуем перезапустить
        subprocess.run(["systemctl", "restart", SERVICE_NAME])
        time.sleep(3)
        
        if not is_service_active():
            send_telegram_alert(
                f"🚨 <b>ВНИМАНИЕ! БОТ УПАЛ И НЕ ОТВЕЧАЕТ!</b>\n\n"
                f"Сервис <code>{SERVICE_NAME}</code> перестал работать и не смог перезапуститься."
            )
