import re
import asyncio
import pandas as pd
from datetime import datetime, timezone, timedelta
from core.database import add_alert, get_all_alerts, add_timer, get_pending_timers, delete_timer
from core.fetcher import fetch_klines

MSK_TZ = timezone(timedelta(hours=3))

ALL_SYMBOLS = [
    "BTC-USDT", "ETH-USDT", "SOL-USDT", "KAS-USDT", 
    "LTC-USDT", "DOT-USDT", "DOGE-USDT", "ATOM-USDT", "ADA-USDT"
]

MONTHS_RU = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12
}

def clean_symbol(symbol: str) -> str:
    return symbol.replace("-USDT", "").replace("USDT", "").upper()

def parse_asset(text_lower: str) -> str:
    if any(w in text_lower for w in ["эфир", "eth"]): return "ETH-USDT"
    if any(w in text_lower for w in ["солана", "sol", "солану"]): return "SOL-USDT"
    if any(w in text_lower for w in ["каспа", "kas"]): return "KAS-USDT"
    if any(w in text_lower for w in ["доги", "doge"]): return "DOGE-USDT"
    if any(w in text_lower for w in ["атом", "atom"]): return "ATOM-USDT"
    if any(w in text_lower for w in ["ада", "ada"]): return "ADA-USDT"
    if any(w in text_lower for w in ["лайт", "ltc"]): return "LTC-USDT"
    if any(w in text_lower for w in ["дот", "dot"]): return "DOT-USDT"
    return "BTC-USDT"

def get_row_datetime(row):
    for col in ['open_time', 'time', 'timestamp', 'datetime']:
        if col in row:
            val = row[col]
            if isinstance(val, (int, float)):
                unit = 'ms' if val > 1e11 else 's'
                return pd.to_datetime(val, unit=unit, utc=True).astimezone(MSK_TZ)
            elif isinstance(val, (pd.Timestamp, datetime)):
                if val.tzinfo is None:
                    return val.replace(tzinfo=timezone.utc).astimezone(MSK_TZ)
                return val.astimezone(MSK_TZ)
    if hasattr(row, 'name') and isinstance(row.name, (pd.Timestamp, datetime)):
        val = row.name
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc).astimezone(MSK_TZ)
        return val.astimezone(MSK_TZ)
    return None

def format_alerts_table(chat_id: int):
    rows = get_all_alerts(chat_id=chat_id)
    if not rows:
        return "🔔 <b>У вас нет активных ценовых алертов.</b>", None
    
    table_text = "<b>🔔 АКТИВНЫЕ ЦЕНОВЫЕ АЛЕРТЫ:</b>\n<pre>"
    table_text += f"{'№':<3} | {'АКТ':<5} | {'УРОВЕНЬ':<10} | {'ОПИСАНИЕ'}\n"
    table_text += "-" * 38 + "\n"
    
    inline_buttons = []
    row_btns = []
    
    for idx, row in enumerate(rows, start=1):
        coin = clean_symbol(row['symbol'])
        price = f"{row['target_price']:.4f}".rstrip('0').rstrip('.')
        comment = row['comment'] or 'Алерт'
        
        table_text += f"{idx:<3} | {coin:<5} | {price:<10} | {comment}\n"
        
        row_btns.append({"text": f"❌ #{idx}", "callback_data": f"del_alert_{row['id']}"})
        if len(row_btns) == 3:
            inline_buttons.append(row_btns)
            row_btns = []
            
    if row_btns:
        inline_buttons.append(row_btns)
        
    table_text += "</pre>"
    return table_text, inline_buttons

async def process_ai_message(text: str, chat_id: int):
    text_lower = text.lower()
    now_msk = datetime.now(MSK_TZ)

    # 1. ТАЙМЕРЫ И БУДИЛЬНИКИ (С сохранением в БД)
    if any(w in text_lower for w in ["таймер", "будильник", "напомни"]):
        time_match = re.search(r'(\d{1,2})[\.:\s]+(\d{2})', text_lower)
        if time_match:
            target_hour = int(time_match.group(1))
            target_min = int(time_match.group(2))
            
            target_time = now_msk.replace(hour=target_hour, minute=target_min, second=0, microsecond=0)
            if target_time <= now_msk:
                target_time += timedelta(days=1)
                
            wait_min = int((target_time - now_msk).total_seconds() // 60)
            add_timer(chat_id, target_time, f"⏰ Время {target_hour:02d}:{target_min:02d} МСК!")
            return {"content": f"⏰ <b>Таймер установлен на {target_hour:02d}:{target_min:02d} МСК</b> (через {wait_min} мин).", "markup": None}

    # Флаг пакетной команды
    is_all_pairs = any(w in text_lower for w in ["каждую валютную пару", "все пары", "все монеты", "каждую пару", "все криптовалюты"])
    target_symbols = ALL_SYMBOLS if is_all_pairs else [parse_asset(text_lower)]

    # 2. ПОИСК 1-ЧАСОВОГО И 4-ЧАСОВОГО БАРА
    is_1h = any(w in text_lower for w in ["1ч", "1-часов", "часовой", "1 час", "часового"])
    is_4h = any(w in text_lower for w in ["4ч", "4-часов", "четырехчасов", "4 часа", "4 час"])
    
    if is_1h or is_4h:
        tf = "1h" if is_1h else "4h"
        tf_label = "1H" if is_1h else "4H"
        hours_step = 1 if is_1h else 4
        
        hour_match = re.search(r'(\d{1,2})\s*(?:часов|часа|ч|:00)?', text_lower)
        target_hour = int(hour_match.group(1)) if hour_match else now_msk.hour
        
        target_date = now_msk.date()
        if "вчера" in text_lower:
            target_date -= timedelta(days=1)
        elif "позавчера" in text_lower:
            target_date -= timedelta(days=2)
            
        for sym in target_symbols:
            df = await fetch_klines(sym, tf, limit=50)
            if df is not None and not df.empty:
                matched_candle = None
                for idx, row in df.iterrows():
                    dt_open = get_row_datetime(row)
                    if dt_open:
                        dt_close = dt_open + timedelta(hours=hours_step)
                        if dt_open.date() == target_date and (dt_close.hour == target_hour or dt_open.hour == target_hour):
                            matched_candle = row
                            break
                
                if matched_candle is None and len(df) >= 2:
                    matched_candle = df.iloc[-2]
                
                if matched_candle is not None:
                    c_high = float(matched_candle['high'])
                    c_low = float(matched_candle['low'])
                    dt_open = get_row_datetime(matched_candle)
                    time_str = f"{tf_label} {dt_open.strftime('%d.%m %H:00')}" if dt_open else tf_label
                    
                    if "максимум" in text_lower or "хай" in text_lower or not ("минимум" in text_lower or "лоу" in text_lower):
                        add_alert(symbol=sym, target_price=c_high, alert_type="CROSS", comment=f"High {time_str}", chat_id=chat_id)
                    if "минимум" in text_lower or "лоу" in text_lower or not ("максимум" in text_lower or "хай" in text_lower):
                        add_alert(symbol=sym, target_price=c_low, alert_type="CROSS", comment=f"Low {time_str}", chat_id=chat_id)
        
        table_text, inline_btns = format_alerts_table(chat_id)
        return {"content": table_text, "markup": inline_btns}

    # 3. ПОИСК ДНЕВНОГО БАРА (1D)
    day_target_dt = None
    date_match = re.search(r'(\d{1,2})\s+([а-я+]+)', text_lower)
    if date_match:
        day_num = int(date_match.group(1))
        month_str = date_match.group(2)
        if month_str in MONTHS_RU:
            month_num = MONTHS_RU[month_str]
            year_num = now_msk.year
            try:
                day_target_dt = datetime(year_num, month_num, day_num, tzinfo=MSK_TZ)
            except ValueError: pass

    if not day_target_dt:
        if "позавчера" in text_lower:
            day_target_dt = now_msk - timedelta(days=2)
        elif "вчера" in text_lower or any(w in text_lower for w in ["минимум", "максимум", "хай", "лоу", "бар"]):
            day_target_dt = now_msk - timedelta(days=1)

    if day_target_dt:
        date_label = day_target_dt.strftime("%d.%m")
        for sym in target_symbols:
            df_1d = await fetch_klines(sym, "1d", limit=30)
            if df_1d is not None and not df_1d.empty:
                matched_candle = None
                for idx, row in df_1d.iterrows():
                    dt_open = get_row_datetime(row)
                    if dt_open and dt_open.date() == day_target_dt.date():
                        matched_candle = row
                        break
                
                if matched_candle is None and len(df_1d) >= 2:
                    matched_candle = df_1d.iloc[-2]

                if matched_candle is not None:
                    d_high = float(matched_candle['high'])
                    d_low = float(matched_candle['low'])
                    
                    if "максимум" in text_lower or "хай" in text_lower or not ("минимум" in text_lower or "лоу" in text_lower):
                        add_alert(symbol=sym, target_price=d_high, alert_type="CROSS", comment=f"High {date_label}", chat_id=chat_id)
                    if "минимум" in text_lower or "лоу" in text_lower or not ("максимум" in text_lower or "хай" in text_lower):
                        add_alert(symbol=sym, target_price=d_low, alert_type="CROSS", comment=f"Low {date_label}", chat_id=chat_id)
                
        table_text, inline_btns = format_alerts_table(chat_id)
        return {"content": table_text, "markup": inline_btns}

    # 4. ОБЫЧНАЯ ЦЕНА
    price_match = re.search(r'(\d+[\.,]?\d*)', text)
    if price_match:
        try:
            target_price = float(price_match.group(1).replace(',', '.'))
            add_alert(symbol=target_symbols[0], target_price=target_price, alert_type="CROSS", comment="Ценовой уровень", chat_id=chat_id)
            table_text, inline_btns = format_alerts_table(chat_id)
            return {"content": table_text, "markup": inline_btns}
        except ValueError: pass

    table_text, inline_btns = format_alerts_table(chat_id)
    return {"content": table_text, "markup": inline_btns}

async def timer_checker_loop(bot):
    """Фоновая проверка срабатывания таймеров из БД"""
    while True:
        try:
            now = datetime.now(MSK_TZ)
            pending = get_pending_timers()
            for t in pending:
                trig_dt = datetime.fromisoformat(t['trigger_time'])
                if now >= trig_dt:
                    await bot.send_message(chat_id=t['chat_id'], text=f"🔔 <b>НАПОМИНАНИЕ:</b>\n{t['message']}", parse_mode="HTML")
                    delete_timer(t['id'])
        except Exception as e:
            pass
        await asyncio.sleep(2)
