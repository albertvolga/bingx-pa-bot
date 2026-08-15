import datetime
import asyncio
import re
from core.nlp_parser import parse_user_intent
from core.database import add_alert, get_all_alerts, delete_alert
from core.bingx import fetch_bingx_candles

SYMBOL_MAP = {
    # Драгметаллы и товары
    "SILVER": "SILVER", "XAG": "SILVER", "СЕРЕБРО": "SILVER", "СЕРЕБРУ": "SILVER", "СЕРЕБРА": "SILVER",
    "PAXG": "PAXG", "XAU": "PAXG", "GOLD": "PAXG", "ЗОЛОТО": "PAXG", "ЗОЛОТУ": "PAXG", "ЗОЛОТА": "PAXG",
    "NATURALGAS": "NATURALGAS", "NG": "NATURALGAS", "ГАЗ": "NATURALGAS", "ГАЗА": "NATURALGAS",
    "OILBRENT": "OILBRENT", "BRENT": "OILBRENT", "OIL": "OILBRENT", "НЕФТЬ": "OILBRENT", "НЕФТИ": "OILBRENT",

    # Криптовалюты
    "KAS": "KAS", "КАСПА": "KAS", "КАССПА": "KAS", "КАСПУ": "KAS",
    "ATOM": "ATOM", "АТОМ": "ATOM", "КОСМОС": "ATOM",
    "XMR": "XMR", "МОНЕРО": "XMR", "МОНЕЙРО": "XMR",
    "DOGE": "DOGE", "ДОДЖ": "DOGE", "ДОДЖУ": "DOGE", "ДОГИ": "DOGE",
    "ADA": "ADA", "КАРДАНО": "ADA", "АДА": "ADA", "АДУ": "ADA",
    "LTC": "LTC", "ЛАЙТКОИН": "LTC", "ЛАЙТКОЙН": "LTC", "ЛАЙТ": "LTC", "ЛАЙТА": "LTC",
    "SOL": "SOL", "СОЛАНА": "SOL", "СОЛАНЕ": "SOL", "СОЛАНУ": "SOL", "СОЛ": "SOL",
    "ETH": "ETH", "ЭФИР": "ETH", "ЭФИРУ": "ETH", "ЭФИРЕ": "ETH", "ЭФИРИУМ": "ETH",
    "BTC": "BTC", "БИТКОИН": "BTC", "БИТКОИНУ": "BTC", "БИТОК": "BTC", "БИТКУ": "BTC",
    "XRP": "XRP", "РИПЛ": "XRP", "РИППЛ": "XRP", "РИПЛА": "XRP",
    "DOT": "DOT", "ПОЛКАДОТ": "DOT", "ДОТ": "DOT", "ДОТУ": "DOT"
}

def clean_symbol(symbol: str) -> str:
    sym = symbol.upper().replace("-USDT", "").replace(".P", "").replace(".F", "").replace("USDT", "")
    return SYMBOL_MAP.get(sym, sym)

def extract_symbol_from_text(text: str) -> str:
    text_upper = text.upper()
    words = re.findall(r'[A-ZА-Я0-9]+', text_upper)
    for w in words:
        if w in SYMBOL_MAP:
            return SYMBOL_MAP[w]
    return None  # Больше никакого фолбэка на BTC!

def parse_timeframe_and_offset(text: str):
    t_lower = text.lower()
    
    tf = "1h"
    if any(k in t_lower for k in ["дневн", "1d", "день", "дневном", "дневного"]):
        tf = "1d"
    elif any(k in t_lower for k in ["4h", "4ч", "4-часов", "4часов"]):
        tf = "4h"
    elif any(k in t_lower for k in ["1w", "1нед", "недельн"]):
        tf = "1w"
    elif any(k in t_lower for k in ["1h", "1ч", "часов"]):
        tf = "1h"

    offset = -2
    if "позавчера" in t_lower:
        offset = -3
        
    return tf, offset

def format_alerts_table(chat_id: int = None, alerts_list=None):
    if alerts_list is None and chat_id is not None:
        alerts_list = get_all_alerts(chat_id)
        
    if not alerts_list:
        return "📋 У вас пока нет активных алертов.", []
    
    text = "<b>📌 Ваши активные алерты:</b>\n\n<pre>"
    text += f"{'ID':<4} | {'Монета':<6} | {'Уровень':<10} | {'Примечание'}\n"
    text += "-" * 42 + "\n"
    
    buttons = []
    for a in alerts_list:
        if isinstance(a, dict):
            aid = a.get("id", "-")
            sym = a.get("symbol", "-")
            price = a.get("price", 0.0)
            note = a.get("note", "")
        else:
            aid, sym, price, note = a[0], a[2], a[3], a[4] if len(a) > 4 else ""
            
        text += f"#{aid:<3} | {sym:<6} | {price:<10.2f} | {note}\n"
        buttons.append({"text": f"❌ #{aid}", "callback_data": f"del_alert_{aid}"})
    
    text += "</pre>"
    return text, buttons

async def timer_checker_loop(bot=None):
    while True:
        await asyncio.sleep(60)

async def process_ai_message(text: str, chat_id: int) -> dict:
    parsed = parse_user_intent(text)
    
    if parsed.get("type") == "alert" or any(k in text.lower() for k in ["алерт", "поставь", "уровень", "уведомление", "напоминание"]):
        symbol_short = extract_symbol_from_text(text)
        
        if not symbol_short:
            return {"type": "chat", "text": "❌ <b>Не удалось определить монету.</b> Уточните название актива (например, <i>KAS, Солана, Лайткоин</i>)."}

        bingx_symbol = f"{symbol_short}-USDT"
        
        target_price = parsed.get("target_price")
        added_alerts = []

        # Вариант 1: Точная цена
        if target_price is not None and parsed.get("level_type") == "exact":
            note = "Уровень пользователя"
            aid = add_alert(chat_id=chat_id, symbol=symbol_short, target_price=target_price, note=note)
            added_alerts.append({"id": aid, "symbol": symbol_short, "price": target_price, "note": note})
            return {"type": "alert_created", "alerts": added_alerts}

        # Вариант 2: Расчет по свечам (High / Low / High+Low)
        tf, candle_offset = parse_timeframe_and_offset(text)
        
        t_lower = text.lower()
        if "хай" in t_lower and "лоу" in t_lower:
            level_type = "prev_candle_high_low"
        elif "хай" in t_lower:
            level_type = "prev_candle_high"
        elif "лоу" in t_lower:
            level_type = "prev_candle_low"
        else:
            level_type = "prev_candle_high_low"

        klines = await fetch_bingx_candles(bingx_symbol, timeframe=tf, limit=10, interval=tf)
        if not klines or len(klines) < abs(candle_offset):
            return {"type": "chat", "text": f"❌ Не удалось получить данные по свечам для <b>{symbol_short}</b> ({tf})."}

        target_candle = klines[candle_offset]
        c_high = float(target_candle["high"])
        c_low = float(target_candle["low"])
        
        timestamp_ms = float(target_candle.get("time", target_candle.get("timestamp", 0)))
        if timestamp_ms > 0:
            dt = datetime.datetime.fromtimestamp(timestamp_ms / 1000, tz=datetime.timezone.utc) + datetime.timedelta(hours=3)
            time_str = dt.strftime("%d.%m %H:%M")
        else:
            time_str = "свеча"

        tf_label = tf.upper()

        if level_type == "prev_candle_high_low":
            desc_h = f"High {tf_label} ({time_str})"
            desc_l = f"Low {tf_label} ({time_str})"
            
            aid_h = add_alert(chat_id=chat_id, symbol=symbol_short, target_price=c_high, note=desc_h)
            aid_l = add_alert(chat_id=chat_id, symbol=symbol_short, target_price=c_low, note=desc_l)
            
            added_alerts.append({"id": aid_h, "symbol": symbol_short, "price": c_high, "note": desc_h})
            added_alerts.append({"id": aid_l, "symbol": symbol_short, "price": c_low, "note": desc_l})

        elif level_type == "prev_candle_high":
            desc_h = f"High {tf_label} ({time_str})"
            aid_h = add_alert(chat_id=chat_id, symbol=symbol_short, target_price=c_high, note=desc_h)
            added_alerts.append({"id": aid_h, "symbol": symbol_short, "price": c_high, "note": desc_h})

        elif level_type == "prev_candle_low":
            desc_l = f"Low {tf_label} ({time_str})"
            aid_l = add_alert(chat_id=chat_id, symbol=symbol_short, target_price=c_low, note=desc_l)
            added_alerts.append({"id": aid_l, "symbol": symbol_short, "price": c_low, "note": desc_l})

        return {"type": "alert_created", "alerts": added_alerts}

    return {"type": "chat", "text": parsed.get("reply", "Принято.")}
