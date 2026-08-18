import datetime
import asyncio
import re
from core.nlp_parser import parse_user_intent
from core.database import add_alert, get_all_alerts, delete_alert
from core.bingx import fetch_bingx_candles
from config import SYMBOL_MAP # Импортируем SYMBOL_MAP из config.py
from core.formatter import format_alerts_table # Импортируем измененную функцию

def clean_symbol(symbol: str) -> str:
    """
    Очищает символ, убирая суффиксы USDT и преобразуя к короткому имени, если есть в SYMBOL_MAP.
    """
    sym_cleaned = symbol.upper().replace("-USDT", "").replace(".P", "").replace(".F", "").replace("USDT", "")
    
    # Ищем короткое имя среди ключей SYMBOL_MAP
    if sym_cleaned in SYMBOL_MAP:
        return sym_cleaned
        
    # Ищем полное имя (значение) в SYMBOL_MAP и возвращаем соответствующий ключ
    for short_name, full_name_usdt in SYMBOL_MAP.items():
        if sym_cleaned == full_name_usdt.replace('-USDT', ''):
            return short_name
            
    return sym_cleaned # Если не найдено, возвращаем как есть

def extract_symbol_from_text(text: str) -> str:
    """
    Извлекает символ актива из текста, используя SYMBOL_MAP и русские синонимы.
    Возвращает короткое имя символа (например, 'BTC', 'PAXG').
    """
    t_lower = text.lower()
    
    # Создаем обратный маппинг для поиска по русским и полным названиям
    reverse_map = {}
    for short_name, full_name_usdt in SYMBOL_MAP.items():
        reverse_map[short_name.lower()] = short_name # btc -> BTC
        reverse_map[full_name_usdt.lower()] = short_name # btc-usdt -> BTC
        reverse_map[full_name_usdt.replace('-USDT', '').lower()] = short_name # btc -> BTC
        
    # Добавляем наиболее распространенные русские эквиваленты и синонимы
    russian_synonyms = {
        "золото": "PAXG", "xau": "PAXG", "голд": "PAXG",
        "серебро": "SILVER", "xag": "SILVER", "сильвер": "SILVER",
        "каспа": "KAS", "касспа": "KAS",
        "атом": "ATOM", "космос": "ATOM",
        "монеро": "XMR", "монейро": "XMR",
        "доги": "DOGE", "додг": "DOGE",
        "ада": "ADA", "кардано": "ADA",
        "лайткоин": "LTC", "лайт": "LTC",
        "солана": "SOL", "сол": "SOL",
        "эфир": "ETH", "эфириум": "ETH",
        "биткоин": "BTC", "биток": "BTC",
        "рипл": "XRP", "риппл": "XRP",
        "дот": "DOT", "полкадот": "DOT",
        "природный газ": "NG", "газ": "NG",
        "нефть": "OIL"
    }
    reverse_map.update(russian_synonyms)

    words = re.findall(r'[a-zа-я0-9]+', t_lower)
    # Ищем самое длинное совпадение, чтобы избежать ложных срабатываний на "сол" в "солана"
    best_match = None
    best_match_len = 0

    for w in words:
        if w in reverse_map:
            if len(w) > best_match_len:
                best_match = reverse_map[w]
                best_match_len = len(w)
            
    return best_match

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

    # Смещения свечи: -1 = последняя закрытая, -2 = позапрошлая закрытая
    offset = -1 # По умолчанию берем последнюю закрытую свечу
    if "позавчера" in t_lower or "позавчерашнего" in t_lower:
        offset = -2
    elif "вчера" in t_lower or "вчерашнего" in t_lower:
        offset = -1 # Вчерашний дневной бар для D1, или предыдущий бар для H1/H4 и т.д.

    # Парсинг конкретного времени закрытия бара
    time_match = re.search(r'\b(закрытый|закрывшегося|закрывш)\s*в\s*(\d{1,2}(?::\d{2})?)\s*(?:часов|ч|утра|дня|вечера)?', t_lower)
    specific_bar_time = None
    if time_match:
        specific_bar_time = time_match.group(2) # "10" или "10:00"

    return tf, offset, specific_bar_time

async def process_ai_message(text: str, chat_id: int) -> dict:
    parsed = parse_user_intent(text)
    
    # Расширяем условия для срабатывания логики алерта
    if parsed.get("type") == "alert" or any(k in text.lower() for k in ["алерт", "поставь", "уровень", "уведомление", "напоминание", "хай", "лоу", "минимум", "максимум", "когда будет"]):
        symbol_short = extract_symbol_from_text(text)
        
        if not symbol_short:
            return {"type": "chat", "text": "❌ <b>Не удалось определить монету.</b> Уточните название актива (например, <i>KAS, Солана, Лайткоин</i>)."}

        bingx_symbol = f"{symbol_short}-USDT"
        
        target_price = parsed.get("target_price")
        added_alerts = []

        # Парсинг timeframe, offset, specific_bar_time
        tf, candle_offset, specific_bar_time = parse_timeframe_and_offset(text)
        
        t_lower = text.lower()

        # Определение condition (cross_above/cross_below)
        condition = None
        if "выше" in t_lower or "больше" in t_lower or "пробьет вверх" in t_lower:
            condition = "cross_above"
        elif "ниже" in t_lower or "меньше" in t_lower or "пробьет вниз" in t_lower:
            condition = "cross_below"
        # Если не указано, по умолчанию считаем cross (любое пересечение)
        
        # Вариант 1: Точная цена
        if target_price is not None and parsed.get("level_type") == "exact":
            note = f"Уровень пользователя: {target_price}"
            aid = add_alert(chat_id=chat_id, symbol=symbol_short, target_price=target_price, note=note, condition=condition)
            added_alerts.append({"id": aid, "symbol": symbol_short, "price": target_price, "note": note})
            return {"type": "alert_created", "alerts": added_alerts}

        # Вариант 2: Расчет по свечам (High / Low / High+Low)
        level_type = None
        if "хай" in t_lower or "максимум" in t_lower:
            if "лоу" in t_lower or "минимум" in t_lower:
                level_type = "prev_candle_high_low"
            else:
                level_type = "prev_candle_high"
        elif "лоу" in t_lower or "минимум" in t_lower:
            level_type = "prev_candle_low"
        
        if level_type: # Если запрошен уровень по свече
            # Для анализа исторических баров
            # Увеличиваем limit, чтобы точно захватить нужный бар
            klines = await fetch_bingx_candles(bingx_symbol, timeframe=tf, limit=max(10, abs(candle_offset) + 5), interval=tf)
            if not klines or len(klines) < abs(candle_offset):
                return {"type": "chat", "text": f"❌ Не удалось получить достаточно данных по свечам для <b>{symbol_short}</b> ({tf})."}

            target_candle_data = None
            if specific_bar_time:
                # Поиск свечи по времени закрытия (или открытия, в зависимости от API)
                # Предполагаем, что specific_bar_time относится к MSK
                for candle in klines:
                    candle_open_dt_msk = datetime.fromtimestamp(candle['time'] / 1000, tz=timezone.utc).astimezone(datetime.timedelta(hours=3))
                    
                    # Для простоты пока ищем совпадение часа
                    if specific_bar_time.count(':') == 1: # HH:MM
                         if candle_open_dt_msk.strftime("%H:%M") == specific_bar_time:
                            target_candle_data = candle
                            break
                    else: # HH
                         if candle_open_dt_msk.hour == int(specific_bar_time):
                            target_candle_data = candle
                            break
                if target_candle_data is None:
                    return {"type": "chat", "text": f"❌ Не удалось найти свечу для <b>{symbol_short}</b> ({tf}) закрытую в <b>{specific_bar_time}</b>."}
            else:
                target_candle_data = klines[candle_offset]
            
            c_high = float(target_candle_data["high"])
            c_low = float(target_candle_data["low"])
            
            timestamp_ms = float(target_candle_data.get("time", 0))
            if timestamp_ms > 0:
                dt_candle = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).astimezone(datetime.timedelta(hours=3))
                # Время закрытия свечи для примечания
                if tf == "1h": dt_close = dt_candle + timedelta(hours=1)
                elif tf == "4h":
                    ch = dt_candle.hour
                    if ch < 3: next_ch = 3
                    elif ch < 7: next_ch = 7
                    elif ch < 11: next_ch = 11
                    elif ch < 15: next_ch = 15
                    elif ch < 19: next_ch = 19
                    elif ch < 23: next_ch = 23
                    else: next_ch = 3
                    dt_close = dt_candle.replace(hour=next_ch, minute=0, second=0, microsecond=0)
                    if dt_close < dt_candle: dt_close += timedelta(days=1)
                elif tf == "1d": dt_close = dt_candle.replace(hour=3, minute=0, second=0, microsecond=0) + timedelta(days=1)
                elif tf == "1w": dt_close = dt_candle.replace(hour=3, minute=0, second=0, microsecond=0) + timedelta(days=(7 - dt_candle.weekday()))
                else: dt_close = dt_candle + timedelta(hours=1) # Fallback

                time_str = dt_close.strftime("%d.%m %H:%M")
            else:
                time_str = "свеча"

            tf_label = TF_SHORT_MAP.get(tf.lower(), tf).upper()

            if level_type == "prev_candle_high_low":
                desc_h = f"High {tf_label} ({time_str})"
                desc_l = f"Low {tf_label} ({time_str})"
                
                aid_h = add_alert(chat_id=chat_id, symbol=symbol_short, target_price=c_high, note=desc_h, condition="cross")
                aid_l = add_alert(chat_id=chat_id, symbol=symbol_short, target_price=c_low, note=desc_l, condition="cross")
                
                added_alerts.append({"id": aid_h, "symbol": symbol_short, "price": c_high, "note": desc_h})
                added_alerts.append({"id": aid_l, "symbol": symbol_short, "price": c_low, "note": desc_l})

            elif level_type == "prev_candle_high":
                desc_h = f"High {tf_label} ({time_str})"
                aid_h = add_alert(chat_id=chat_id, symbol=symbol_short, target_price=c_high, note=desc_h, condition=condition or "cross_above")
                added_alerts.append({"id": aid_h, "symbol": symbol_short, "price": c_high, "note": desc_h})

            elif level_type == "prev_candle_low":
                desc_l = f"Low {tf_label} ({time_str})"
                aid_l = add_alert(chat_id=chat_id, symbol=symbol_short, target_price=c_low, note=desc_l, condition=condition or "cross_below")
                added_alerts.append({"id": aid_l, "symbol": symbol_short, "price": c_low, "note": desc_l})
            
            return {"type": "alert_created", "alerts": added_alerts}

    return {"type": "chat", "text": parsed.get("reply", "Принято.")}
