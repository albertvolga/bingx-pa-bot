import re
import logging
from datetime import datetime, timedelta, timezone
import pandas as pd
from config import MSK_TZ, SYMBOL_MAP
from core.database import add_alert, get_all_alerts, delete_alert, clear_all_alerts
from core.bingx.candles import fetch_bingx_candles

logger = logging.getLogger(__name__)

# Расширенный словарь синонимов
SYNONYMS = {
    "биткоин": "BTC", "биток": "BTC", "btc": "BTC", "bitcoin": "BTC",
    "эфир": "ETH", "эфириум": "ETH", "eth": "ETH", "ethereum": "ETH",
    "солана": "SOL", "сол": "SOL", "sol": "SOL",
    "каспа": "KAS", "кас": "KAS", "kas": "KAS",
    "рипл": "XRP", "ripple": "XRP", "xrp": "XRP",
    "доги": "DOGE", "doge": "DOGE", "dogecoin": "DOGE",
    "кардано": "ADA", "ada": "ADA",
    "полкадот": "DOT", "dot": "DOT",
    "лайткоин": "LTC", "litecoin": "LTC", "ltc": "LTC",
    "атом": "ATOM", "cosmos": "ATOM", "atom": "ATOM",
    "золото": "XAU", "xau": "XAU", "gold": "XAU",
    "серебро": "XAG", "xag": "XAG", "silver": "XAG",
    "нефть": "OIL", "oil": "OIL",
    "газ": "NG", "ng": "NG",
}

TF_MAP = {
    "1ч": "1h", "1h": "1h", "час": "1h", "часовой": "1h",
    "4ч": "4h", "4h": "4h", "четырехчасовой": "4h", "4 часа": "4h",
    "1д": "1d", "1d": "1d", "день": "1d", "дневной": "1d", "суточный": "1d",
    "1н": "1w", "1w": "1w", "неделя": "1w", "недельный": "1w",
    "15м": "15m", "15m": "15m", "пятнадцатиминутный": "15m",
}

def extract_symbol(text):
    text_lower = text.lower()
    for synonym, symbol in SYNONYMS.items():
        if re.search(r'\b' + re.escape(synonym) + r'\b', text_lower):
            return symbol
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
    elif "позапозавчера" in text_lower:
        return 3
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
    elif tf == "1d":
        base_time = now_msk.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        base_time = now_msk
    
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
    
    alert_keywords = ["алерт", "уведомление", "поставь", "уровень", "пробой", "cross"]
    if not any(kw in text_lower for kw in alert_keywords):
        return {"type": "ignore"}
    
    symbol = extract_symbol(text)
    if not symbol:
        return {"type": "error", "message": "❌ Не удалось распознать актив (биткоин, солана, BTC и т.д.). Уточните название."}
    
    tf = extract_timeframe(text)
    days_ago = parse_relative_date(text)
    target_hour = parse_target_hour(text)
    
    level_type = None
    if "экстремум" in text_lower or "максимум и минимум" in text_lower or "min и max" in text_lower or "хай и лоу" in text_lower:
        level_type = "both"
    elif "хай" in text_lower or "максимум" in text_lower or "high" in text_lower or "верх" in text_lower:
        level_type = "high"
    elif "лоу" in text_lower or "минимум" in text_lower or "low" in text_lower or "низ" in text_lower:
        level_type = "low"
    else:
        level_type = "both"
    
    offset, bar_description = calculate_candle_offset(tf, days_ago, target_hour)
    
    bingx_symbol = f"{symbol}-USDT"
    limit_needed = abs(offset) + 10  # Берем с запасом
    logger.info(f"Запрос свечей для {bingx_symbol}: TF={tf}, Limit={limit_needed}, Offset={offset}")
    
    try:
        klines = await fetch_bingx_candles(bingx_symbol, timeframe=tf, limit=limit_needed)
        
        # Исправленная проверка DataFrame
        if klines is None or klines.empty or len(klines) < abs(offset) + 1:
            return {"type": "error", "message": f"❌ Недостаточно данных для {symbol} ({tf}). Попробуйте другой таймфрейм или проверьте соединение."}
        
        candle_index = len(klines) - 1 - offset
        if candle_index < 0 or candle_index >= len(klines):
             return {"type": "error", "message": f"❌ Ошибка расчета индекса свечи (offset={offset}, всего свечей={len(klines)})."}
             
        candle = klines.iloc[candle_index]
        
        # Безопасное извлечение High и Low
        try:
            high = float(candle['high'])
            low = float(candle['low'])
        except (ValueError, TypeError) as e:
            logger.error(f"Ошибка преобразования цены: {e}, candle={candle}")
            return {"type": "error", "message": "❌ Ошибка чтения данных цены. Попробуйте позже."}
        
        # Безопасное извлечение времени
        time_val = candle.get('time')
        if time_val is None:
            # Если ключа 'time' нет, пробуем 'timestamp' или берем текущее
            time_val = candle.get('timestamp', datetime.now().timestamp() * 1000)
        
        # Конвертация времени в мс, если это Timestamp или datetime
        if hasattr(time_val, 'timestamp'): # Это datetime или Timestamp
            close_time_ms = int(time_val.timestamp() * 1000)
        elif isinstance(time_val, (int, float)):
            close_time_ms = int(time_val)
        else:
            # Пытаемся распарсить строку или берем дефолт
            try:
                close_time_ms = int(float(time_val))
            except:
                close_time_ms = int(datetime.now().timestamp() * 1000)
                
        dt_open = datetime.fromtimestamp(close_time_ms / 1000, tz=timezone.utc).astimezone(MSK_TZ)
        real_bar_desc = f"{tf.upper()} бар от {dt_open.strftime('%d.%m %H:%M')} MSK"
        
        alerts_created = []
        
        if level_type == "both":
            id_high = add_alert(chat_id=chat_id, symbol=symbol, target_price=high, note=f"HIGH: {real_bar_desc}", condition="cross_above", is_recurring=False)
            id_low = add_alert(chat_id=chat_id, symbol=symbol, target_price=low, note=f"LOW: {real_bar_desc}", condition="cross_below", is_recurring=False)
            alerts_created.append({"id": id_high, "type": "HIGH", "price": high})
            alerts_created.append({"id": id_low, "type": "LOW", "price": low})
            
            msg = (
                f"✅ <b>Алерты установлены на {symbol}!</b>\n\n"
                f"📊 <b>Таймфрейм:</b> {tf.upper()}\n"
                f"🕰 <b>Бар:</b> {real_bar_desc}\n\n"
                f"🔼 <b>HIGH:</b> <code>{high}</code> (ID: {id_high})\n"
                f"🔽 <b>LOW:</b> <code>{low}</code> (ID: {id_low})\n\n"
                f"<i>Уведомления придут при пробое уровней.</i>"
            )
        elif level_type == "high":
            id_high = add_alert(chat_id=chat_id, symbol=symbol, target_price=high, note=f"HIGH: {real_bar_desc}", condition="cross_above", is_recurring=False)
            msg = (
                f"✅ <b>Алерт установлен на {symbol}!</b>\n\n"
                f"📊 <b>Таймфрейм:</b> {tf.upper()}\n"
                f"🕰 <b>Бар:</b> {real_bar_desc}\n\n"
                f"🔼 <b>HIGH:</b> <code>{high}</code> (ID: {id_high})"
            )
        elif level_type == "low":
            id_low = add_alert(chat_id=chat_id, symbol=symbol, target_price=low, note=f"LOW: {real_bar_desc}", condition="cross_below", is_recurring=False)
            msg = (
                f"✅ <b>Алерт установлен на {symbol}!</b>\n\n"
                f"📊 <b>Таймфрейм:</b> {tf.upper()}\n"
                f"🕰 <b>Бар:</b> {real_bar_desc}\n\n"
                f"🔽 <b>LOW:</b> <code>{low}</code> (ID: {id_low})"
            )
        else:
            msg = "❌ Не определен тип уровня."
            
        return {"type": "success", "message": msg, "alerts": alerts_created}
        
    except Exception as e:
        logger.error(f"Критическая ошибка при создании AI-алерта: {e}", exc_info=True)
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
