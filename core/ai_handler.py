import datetime
import asyncio
import re
from core.nlp_parser import parse_user_intent
from core.database import add_alert, get_all_alerts, delete_alert
from core.bingx.candles import fetch_bingx_candles # Corrected import for fetch_bingx_candles
from config import SYMBOL_MAP # Импортируем SYMBOL_MAP из config.py
from core.formatter import format_alerts_table, TF_SHORT_MAP, MSK_TZ # Импортируем измененную функцию и TF_SHORT_MAP, MSK_TZ

# Временное хранилище для ожидающих уточнений алертов (НЕПЕРСИСТЕНТНО!)
# В продакшене требуется БД или ai_dialog.py с сохранением контекста.
pending_alert_clarifications = {}

def clean_symbol(symbol: str) -> str:
    """
    Очищает символ, убирая суффиксы USDT и преобразует к короткому имени, если есть в SYMBOL_MAP.
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
        "биткоин": "BTC", "биток": "BTC", "биткоина": "BTC",
        "рипл": "XRP", "риппл": "XRP", "рипла": "XRP", "риппла": "XRP",
        "дот": "DOT", "полкадот": "DOT", "дота": "DOT", "полкадота": "DOT",
        "природный газ": "NG", "газ": "NG", "газа": "NG",
        "нефть": "OIL", "нефти": "OIL",
        "эфира": "ETH", "эфириума": "ETH", "каспы": "KAS", "атома": "ATOM", "монеро": "XMR", "монейро": "XMR",
        "доги": "DOGE", "доджа": "DOGE", "ады": "ADA", "кардано": "ADA", "карданы": "ADA",
        "лайткоина": "LTC", "лайта": "LTC", "соланы": "SOL", "сола": "SOL", "золота": "PAXG", "серебра": "SILVER"
    }
    reverse_map.update(russian_synonyms)

    # Улучшаем парсинг: ищем слова, которые могут быть символами или их синонимами
    # Исключаем короткие слова, которые могут быть частью других
    all_possible_terms = list(reverse_map.keys())
    # Сортируем по длине в убывающем порядке, чтобы более длинные совпадения имели приоритет
    all_possible_terms.sort(key=len, reverse=True)

    found_symbol = None
    for term in all_possible_terms:
        # Проверяем, что термин является отдельным словом или частью начала/конца
        if re.search(r'\b' + re.escape(term) + r'\b', t_lower):
            found_symbol = reverse_map[term]
            break # Найден самый длинный подходящий термин, используем его

    return found_symbol
    best_match = None
    best_match_len = 0

    for w in words:
        if w in reverse_map:
            if len(w) > best_match_len:
                best_match = reverse_map[w]
                best_match_len = len(w)
            
    return tf, offset, specific_bar_time

async def process_ai_message(text: str, chat_id: int) -> dict:
    original_text = text # Сохраняем оригинальный текст для повторной обработки
    
    # Проверяем, есть ли ожидающий алерт для этого чата
    if chat_id in pending_alert_clarifications:
        # Если пользователь прислал только символ или короткое название
        symbol_clarified = extract_symbol_from_text(text)
        if symbol_clarified:
            # Используем уточненный символ и исходный запрос
            pending_data = pending_alert_clarifications.pop(chat_id)
            original_alert_text = pending_data["original_text"]
            
            # Попробуем заменить/вставить уточненный символ в исходный запрос.
            # Это упрощенный подход, если исходный текст мог содержать нераспознанный символ,
            # мы просто добавляем уточненный символ в начало для перепарсинга.
            # Если исходный текст был только "поставь алерт на 0.1249", то теперь будет "KAS поставь алерт на 0.1249"
            text_with_clarified_symbol = f"{symbol_clarified} {original_alert_text}"
            return await _process_alert_creation_logic(text_with_clarified_symbol, chat_id, is_clarification=True)
        else:
            pending_alert_clarifications.pop(chat_id, None) # Очищаем, если уточнение не удалось
            return {"type": "chat", "text": "❌ <b>Не удалось распознать монету из вашего уточнения.</b> Пожалуйста, повторите запрос полностью."}
    
    # Основная логика обработки
    return await _process_alert_creation_logic(original_text, chat_id)


async def _process_alert_creation_logic(text: str, chat_id: int, is_clarification: bool = False) -> dict:
    """Внутренняя логика создания алертов, выделенная для повторного использования."""
    parsed = parse_user_intent(text)
    t_lower = text.lower()

    is_alert_intent = parsed.get("type") == "alert" or any(k in t_lower for k in ["алерт", "поставь", "уровень", "уведомление", "напоминание", "хай", "лоу", "минимум", "максимум", "когда будет", "cross"])

    if is_alert_intent:
        symbol_short = extract_symbol_from_text(text)
        
        if not symbol_short:
            # Если не удалось определить монету, сохраняем запрос и просим уточнение
            if not is_clarification: # Просим уточнение только если это не уже уточненный запрос
                pending_alert_clarifications[chat_id] = {"original_text": text}
                return {"type": "chat", "text": "❌ <b>Не удалось определить монету.</b> Уточните название актива (например, <i>KAS, Солана, Лайткоин</i>)."}
            else:
                return {"type": "chat", "text": "❌ <b>Не удалось определить монету даже после уточнения.</b> Повторите запрос, пожалуйста."}

        bingx_symbol = f"{symbol_short}-USDT" # Формируем полное имя для BingX
        
        target_price = parsed.get("target_price")
        added_alerts = []

        # Парсинг timeframe, offset, specific_bar_time
        tf, candle_offset, specific_bar_time = parse_timeframe_and_offset(text)
        
        # Определение condition (cross_above/cross_below)
        condition = None
        if "выше" in t_lower or "больше" in t_lower or "пробьет вверх" in t_lower:
            condition = "cross_above"
        elif "ниже" in t_lower or "меньше" in t_lower or "пробьет вниз" in t_lower:
            condition = "cross_below"
        elif "cross" in t_lower or "пересечет" in t_lower: # Добавил явное условие для "cross"
            condition = "cross"
        # Если не указано, по умолчанию считаем cross (любое пересечение)
        
        # Вариант 1: Точная цена
        if target_price is not None and parsed.get("level_type") == "exact":
            note = f"Уровень пользователя: {target_price}"
            aid = add_alert(chat_id=chat_id, symbol=symbol_short, target_price=target_price, note=note, condition=condition)
            added_alerts.append({"id": aid, "symbol": symbol_short, "price": target_price, "note": note})
            return {"type": "alert_created", "alerts": added_alerts}

        # Вариант 2: Расчет по свечам (High / Low / High+Low)
        level_type = None
        if "хай" in t_lower or "максимум" in t_lower or "high" in t_lower:
            if "лоу" in t_lower or "минимум" in t_lower or "low" in t_lower:
                level_type = "prev_candle_high_low"
            else:
                level_type = "prev_candle_high"
        elif "лоу" in t_lower or "минимум" in t_lower or "low" in t_lower:
            level_type = "prev_candle_low"
        
        if level_type: # Если запрошен уровень по свече
            # Для анализа исторических баров
            # Увеличиваем limit, чтобы точно захватить нужный бар. BingX возвращает *закрытые* свечи.
            klines = await fetch_bingx_candles(bingx_symbol, timeframe=tf, limit=max(10, abs(candle_offset) + 5))
            if not klines or len(klines) < abs(candle_offset):
                return {"type": "chat", "text": f"❌ Не удалось получить достаточно данных по свечам для <b>{symbol_short}</b> ({tf})."}

            target_candle_data = None
            if specific_bar_time:
                # Поиск свечи по времени ОТКРЫТИЯ, так как BingX API возвращает время открытия.
                # Предполагаем, что specific_bar_time относится к MSK
                for candle in klines:
                    # время ОТКРЫТИЯ свечи в UTC
                    candle_open_dt_utc = datetime.fromtimestamp(candle['time'] / 1000, tz=timezone.utc)
                    candle_open_dt_msk = candle_open_dt_utc.astimezone(MSK_TZ)
                    
                    # Для простоты пока ищем совпадение часа/минуты открытия
                    if specific_bar_time.count(':') == 1: # HH:MM
                         if candle_open_dt_msk.strftime("%H:%M") == specific_bar_time:
                            target_candle_data = candle
                            break
                    else: # HH
                         if candle_open_dt_msk.hour == int(specific_bar_time) and candle_open_dt_msk.minute == 0: # Считаем 00 как HH:00
                            target_candle_data = candle
                            break
                if target_candle_data is None:
                    return {"type": "chat", "text": f"❌ Не удалось найти свечу для <b>{symbol_short}</b> ({tf}) открывшуюся в <b>{specific_bar_time}</b> МСК."}
            else:
                # Берем свечу по смещению. -1 это последний закрытый бар.
                target_candle_data = klines[candle_offset]
            
            c_high = float(target_candle_data["high"])
            c_low = float(target_candle_data["low"])
            
            timestamp_ms = float(target_candle_data.get("time", 0))
            if timestamp_ms > 0:
                dt_candle_open = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).astimezone(MSK_TZ)
                
                # Время ЗАКРЫТИЯ свечи для примечания
                dt_close = None
                if tf == "1h": 
                    dt_close = dt_candle_open + timedelta(hours=1)
                elif tf == "4h":
                    current_hour = dt_candle_open.hour
                    next_close_hour = 0
                    if current_hour < 3: next_close_hour = 3
                    elif current_hour < 7: next_close_hour = 7
                    elif current_hour < 11: next_close_hour = 11
                    elif current_hour < 15: next_close_hour = 15
                    elif current_hour < 19: next_close_hour = 19
                    elif current_hour < 23: next_close_hour = 23
                    else: next_close_hour = 3 # For 23:xx current candle, next closes at 03:00 next day
                    
                    dt_close = dt_candle_open.replace(hour=next_close_hour, minute=0, second=0, microsecond=0)
                    if dt_close < dt_candle_open: dt_close += timedelta(days=1) # Handle day rollover
                elif tf == "1d": 
                    dt_close = dt_candle_open.replace(hour=3, minute=0, second=0, microsecond=0) + timedelta(days=1)
                elif tf == "1w": 
                    # 1w candle opens on Monday 03:00 MSK, closes next Monday 03:00 MSK
                    dt_close = dt_candle_open.replace(hour=3, minute=0, second=0, microsecond=0) + timedelta(days=(7 - dt_candle_open.weekday())) # Next Monday 03:00 MSK
                    if dt_close < dt_candle_open: dt_close += timedelta(days=7) # Ensure it's next Monday if current is also Monday
                else: dt_close = dt_candle_open + timedelta(hours=1) # Fallback for other TFs

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

    # Если это не алерт, или не удалось распарсить
    pending_alert_clarifications.pop(chat_id, None) # Очищаем, если запрос не привел к алерту
    return {"type": "chat", "text": parsed.get("reply", "Принято.")}
