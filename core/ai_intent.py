import re
import logging
from datetime import datetime, timedelta, timezone
from config import MSK_TZ, SYMBOL_MAP
from core.database import add_alert
from core.bingx.candles import fetch_bingx_candles
import pandas as pd

logger = logging.getLogger(__name__)

# Расширенный словарь синонимов
SYNONYMS = {
    "биткоин": "BTC", "биток": "BTC", "btc": "BTC", "bitcoin": "BTC", "битка": "BTC", "биткойн": "BTC",
    "эфир": "ETH", "эфириум": "ETH", "eth": "ETH", "ethereum": "ETH", "эфира": "ETH", "эфире": "ETH",
    "солана": "SOL", "сол": "SOL", "sol": "SOL", "соланы": "SOL", "сола": "SOL",
    "каспа": "KAS", "кас": "KAS", "kas": "KAS", "каспы": "KAS", "каспе": "KAS",
    "рипл": "XRP", "ripple": "XRP", "xrp": "XRP", "рипла": "XRP",
    "доги": "DOGE", "doge": "DOGE", "dogecoin": "DOGE", "дог": "DOGE",
    "кардано": "ADA", "ada": "ADA", "карданы": "ADA",
    "полкадот": "DOT", "dot": "DOT", "полкадота": "DOT",
    "лайткоин": "LTC", "litecoin": "LTC", "ltc": "LTC", "лайт": "LTC",
    "атом": "ATOM", "cosmos": "ATOM", "atom": "ATOM",
    "золото": "XAU", "xau": "XAU", "gold": "XAU", "аурум": "XAU",
    "серебро": "XAG", "xag": "XAG", "silver": "XAG",
    "нефть": "OIL", "oil": "OIL", "брент": "OIL",
    "газ": "NG", "ng": "NG", "naturalgas": "NG",
}

TF_MAP = {
    "1ч": "1h", "1h": "1h", "час": "1h", "часовой": "1h", "часовика": "1h",
    "4ч": "4h", "4h": "4h", "четырехчасовой": "4h", "4 часа": "4h", "четырехчасовика": "4h",
    "1д": "1d", "1d": "1d", "день": "1d", "дневной": "1d", "суточный": "1d", "дневика": "1d",
    "1н": "1w", "1w": "1w", "неделя": "1w", "недельный": "1w", "недельки": "1w",
    "15м": "15m", "15m": "15m",
}

def extract_symbol(text):
    text_lower = text.lower()
    # Сортируем по длине, чтобы "биткоин" матчилось раньше "бит"
    sorted_keys = sorted(SYNONYMS.keys(), key=len, reverse=True)
    for synonym in sorted_keys:
        if re.search(r'\b' + re.escape(synonym) + r'\b', text_lower):
            return SYNONYMS[synonym]
    # Проверка по тикерам (BTC, ETH и т.д.)
    for symbol in SYMBOL_MAP.keys():
        if re.search(r'\b' + re.escape(symbol) + r'\b', text.upper()):
            return symbol
    return None

def extract_timeframe(text):
    text_lower = text.lower()
    sorted_tfs = sorted(TF_MAP.keys(), key=len, reverse=True)
    for tf_key in sorted_tfs:
        if re.search(r'\b' + re.escape(tf_key) + r'\b', text_lower):
            return TF_MAP[tf_key]
    return "1d"

def parse_relative_date(text):
    text_lower = text.lower()
    if "позавчера" in text_lower or "позавчерашний" in text_lower:
        return 2
    elif "вчера" in text_lower or "вчерашний" in text_lower:
        return 1
    elif "сегодня" in text_lower or "текущий" in text_lower:
        return 0
    return 0

def parse_target_hour(text):
    match = re.search(r'(?:в |закры[лв][шийся]* )(\d{1,2})(?:\s*(?:часа|часов|:00))?', text.lower())
    if match:
        return int(match.group(1))
    return None

def calculate_candle_offset(tf, days_ago, target_hour=None):
    now_msk = datetime.now(MSK_TZ)
    tf_hours = {"1h": 1, "4h": 4, "1d": 24, "1w": 168}.get(tf, 24)
    
    if tf == "1h":
        base_time = now_msk.replace(minute=0, second=0, microsecond=0)
    elif tf == "4h":
        hour = (now_msk.hour // 4) * 4
        base_time = now_msk.replace(hour=hour, minute=0, second=0, microsecond=0)
    else:
        base_time = now_msk.replace(hour=0, minute=0, second=0, microsecond=0)
    
    target_date = base_time - timedelta(days=days_ago)
    
    if target_hour is not None and tf in ["1h", "4h"]:
        if tf == "4h":
            valid_hours = [3, 7, 11, 15, 19, 23]
            closest_hour = max([h for h in valid_hours if h <= target_hour], default=3)
            target_date = target_date.replace(hour=closest_hour, minute=0, second=0, microsecond=0)
        else:
            target_date = target_date.replace(hour=target_hour % 24, minute=0, second=0, microsecond=0)
            
    diff = base_time - target_date
    hours_diff = int(diff.total_seconds() / 3600)
    offset = int(hours_diff / tf_hours)
    
    date_str = target_date.strftime("%d.%m %H:%M")
    desc = f"{tf.upper()} бар от {date_str} MSK"
    return offset, desc

async def process_ai_command(text, chat_id):
    text_lower = text.lower()
    
    # Ключевые слова для алертов
    alert_keywords = ["алерт", "уведомление", "поставь", "уровень", "пробой", "cross", "достигнет", "упадет", "вырастет"]
    if not any(kw in text_lower for kw in alert_keywords):
        return {"type": "ignore"}
    
    # 1. Символ
    symbol = extract_symbol(text)
    if not symbol:
        return {"type": "error", "message": "❌ Не распознал актив. Напишите название (биток, эфир, солана, каспа)."}
    
    # 2. Таймфрейм
    tf = extract_timeframe(text)
    
    # 3. Дата
    days_ago = parse_relative_date(text)
    target_hour = parse_target_hour(text)
    
    # 4. Тип уровня
    level_type = None
    if "экстремум" in text_lower or "максимум и минимум" in text_lower or "min и max" in text_lower or "хай и лоу" in text_lower:
        level_type = "both"
    elif "хай" in text_lower or "максимум" in text_lower or "high" in text_lower or "верх" in text_lower:
        level_type = "high"
    elif "лоу" in text_lower or "минимум" in text_lower or "low" in text_lower or "низ" in text_lower:
        level_type = "low"
    
    # 5. Конкретная цена? (ищем цифры с точкой или без, но не дату)
    # Ищем паттерн числа: например 2425, 0.0289, 95000
    price_matches = re.findall(r'(\d+[.,]?\d*)', text)
    target_price_val = None
    
    # Фильтруем даты (если число больше 10000, скорее всего это год или часть даты, но для крипты 95000 - цена)
    # Простая эвристика: если есть слово "уровне", "цене", "при достижении" рядом с числом
    if "уровн" in text_lower or "цен" in text_lower or "достижени" in text_lower or "ниже" in text_lower or "выше" in text_lower:
        for match in price_matches:
            val = float(match.replace(',', '.'))
            # Отсекаем годы и часы (например 2024, 15:00)
            if 0.0001 < val < 500000: 
                target_price_val = val
                break
    
    # Если найдена конкретная цена, игнорируем логику баров
    if target_price_val is not None:
        note = f"Цена: {target_price_val}"
        condition = "cross_below" if ("ниже" in text_lower or "упадет" in text_lower) else "cross_above"
        if "cross" in text_lower: condition = "cross"
        
        try:
            aid = add_alert(chat_id=chat_id, symbol=symbol, target_price=target_price_val, note=note, condition=condition, is_recurring=False, tf=tf)
            msg = (
                f"✅ <b>Алерт установлен на {symbol}!</b>\n\n"
                f"🎯 <b>Цена:</b> <code>{target_price_val}</code>\n"
                f"📝 <b>Условие:</b> {'ниже' if condition=='cross_below' else 'выше/пересечение'}\n"
                f"ID: {aid}"
            )
            return {"type": "success", "message": msg}
        except Exception as e:
            logger.error(f"DB Error: {e}")
            return {"type": "error", "message": f"❌ Ошибка БД: {str(e)}"}

    # Логика баров (High/Low)
    if level_type is None:
        level_type = "both" # По умолчанию оба
        
    offset, bar_description = calculate_candle_offset(tf, days_ago, target_hour)
    
    bingx_symbol = f"{symbol}-USDT"
    limit_needed = abs(offset) + 5
    
    try:
        klines = await fetch_bingx_candles(bingx_symbol, timeframe=tf, limit=limit_needed)
        
        if klines is None or klines.empty or len(klines) < abs(offset) + 1:
            return {"type": "error", "message": f"❌ Недостаточно данных для {symbol} ({tf})."}
        
        # Берем нужную свечу
        candle_index = len(klines) - 1 - offset
        if candle_index < 0 or candle_index >= len(klines):
             return {"type": "error", "message": f"❌ Ошибка расчета индекса свечи."}
             
        candle = klines.iloc[candle_index]
        
        # Безопасное получение времени
        time_val = candle.get('time') or candle.get('timestamp') or candle.get('open_time')
        if time_val is None:
            # Если времени нет в явном виде, берем индекс как fallback
            dt_open = datetime.now(MSK_TZ)
        else:
            dt_open = datetime.fromtimestamp(float(time_val) / 1000, tz=timezone.utc).astimezone(MSK_TZ)
        
        high = float(candle['high'])
        low = float(candle['low'])
        
        real_bar_desc = f"{tf.upper()} бар от {dt_open.strftime('%d.%m %H:%M')} MSK"
        alerts_created = []
        
        if level_type == "both":
            id_high = add_alert(chat_id=chat_id, symbol=symbol, target_price=high, note=f"HIGH: {real_bar_desc}", condition="cross_above", is_recurring=False, tf=tf)
            id_low = add_alert(chat_id=chat_id, symbol=symbol, target_price=low, note=f"LOW: {real_bar_desc}", condition="cross_below", is_recurring=False, tf=tf)
            alerts_created.append({"id": id_high, "type": "HIGH", "price": high})
            alerts_created.append({"id": id_low, "type": "LOW", "price": low})
            
            msg = (
                f"✅ <b>Алерты установлены на {symbol}!</b>\n\n"
                f"📊 <b>Таймфрейм:</b> {tf.upper()}\n"
                f"🕰 <b>Бар:</b> {real_bar_desc}\n\n"
                f"🔼 <b>HIGH:</b> <code>{high}</code> (ID: {id_high})\n"
                f"🔽 <b>LOW:</b> <code>{low}</code> (ID: {id_low})"
            )
            return {"type": "success", "message": msg}
            
        elif level_type == "high":
            id_high = add_alert(chat_id=chat_id, symbol=symbol, target_price=high, note=f"HIGH: {real_bar_desc}", condition="cross_above", is_recurring=False, tf=tf)
            msg = f"✅ <b>Алерт на HIGH {symbol}</b>\n🕰 {real_bar_desc}\n🔼 <code>{high}</code> (ID: {id_high})"
            return {"type": "success", "message": msg}
            
        elif level_type == "low":
            id_low = add_alert(chat_id=chat_id, symbol=symbol, target_price=low, note=f"LOW: {real_bar_desc}", condition="cross_below", is_recurring=False, tf=tf)
            msg = f"✅ <b>Алерт на LOW {symbol}</b>\n🕰 {real_bar_desc}\n🔽 <code>{low}</code> (ID: {id_low})"
            return {"type": "success", "message": msg}
            
    except Exception as e:
        logger.error(f"Ошибка при создании AI-алерта: {e}", exc_info=True)
        return {"type": "error", "message": f"❌ Произошла ошибка: {str(e)}"}

def format_alerts_list(alerts):
    if not alerts:
        return "📭 У вас нет активных алертов."
    lines = ["🔔 <b>Ваши активные алерты:</b>\n", "<code>ID | АКТ  | ЦЕНА     | УСЛОВИЕ      | ЗАМЕТКА</code>", "-" * 60]
    for a in alerts:
        aid = a['id']
        sym = a['symbol'].replace("-USDT", "")[:4]
        price = f"{a['target_price']:.2f}"
        cond = a['condition'] or "CROSS"
        note = (a['note'] or "")[:20]
        lines.append(f"{aid:<3}| {sym:<4} | {price:<8} | {cond:<12} | {note}")
    return "\n".join(lines) + "</code>"
