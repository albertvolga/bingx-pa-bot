from datetime import datetime, timedelta
import pytz

def get_bar_close_times():
    """
    Вычисляет корректные времена закрытия баров по МСК для отчета:
    - H1/M15: Округление до ближайшего часа (в 13:55 МСК покажет 14:00)
    - H4: Время последнего закрытого 4-часового бара (в 13:55 покажет 11:00)
    - D1: Всегда 03:00 МСК
    """
    tz_msk = pytz.timezone('Europe/Moscow')
    now = datetime.now(tz_msk)
    
    # 1. H1 и M15: если осталось меньше 10 минут до конца часа, указываем следующий час
    if now.minute >= 50:
        h1_close = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    else:
        h1_close = now.replace(minute=0, second=0, microsecond=0)
        
    # 2. H4: свечи закрываются в 03, 07, 11, 15, 19, 23 МСК
    h4_hours = [3, 7, 11, 15, 19, 23]
    past_h4 = [h for h in h4_hours if h <= now.hour]
    
    if past_h4 and not (now.hour in h4_hours and now.minute < 50):
        last_h4_hour = max(past_h4)
        h4_close = now.replace(hour=last_h4_hour, minute=0, second=0, microsecond=0)
    else:
        # Берём предыдущий закрытый H4
        if past_h4 and now.hour in h4_hours and now.minute < 50:
            past_h4.remove(now.hour)
        if past_h4:
            last_h4_hour = max(past_h4)
            h4_close = now.replace(hour=last_h4_hour, minute=0, second=0, microsecond=0)
        else:
            h4_close = (now - timedelta(days=1)).replace(hour=23, minute=0, second=0, microsecond=0)

    # 3. D1: закрытие всегда в 03:00 МСК
    if now.hour < 3 or (now.hour == 3 and now.minute < 50):
        d1_close = (now - timedelta(days=1)).replace(hour=3, minute=0, second=0, microsecond=0)
    else:
        d1_close = now.replace(hour=3, minute=0, second=0, microsecond=0)
        
    return {
        "M15": h1_close.strftime("%H:%M"),
        "H1": h1_close.strftime("%H:%M"),
        "H4": h4_close.strftime("%H:%M"),
        "D1": d1_close.strftime("%d.%m 03:00")
    }

def format_auto_report(symbol: str, tf_data_dict: dict) -> str:
    """
    Формирует моноширинный табличный автоотчет по заданному активу.
    """
    tz_msk = pytz.timezone('Europe/Moscow')
    now_str = datetime.now(tz_msk).strftime("%d.%m.%y %H:%M")
    close_times = get_bar_close_times()
    
    header = f"📊 Автоотчет на {now_str} МСК:\n"
    header += f"<b>Актив: {symbol}</b>\n\n"
    
    table = "<pre>"
    table += "ТФ  ВРЕМЯ  SMA ПАТ     СОСТ\n"
    table += "---------------------------\n"
    
    timeframes = ["M15", "H1", "H4", "D1"]
    
    for tf in timeframes:
        data = tf_data_dict.get(tf, {})
        time_val = close_times.get(tf, "--:--")
        
        # 1. SMA (24)
        close_price = data.get("close", 0)
        sma24 = data.get("sma24", 0)
        sma_emoji = "🟡" if close_price >= sma24 else "🔴"
        
        # 2. Паттерны (разделяем слэшем, если несколько)
        patterns = data.get("patterns", [])
        if patterns:
            pat_str = "/".join(patterns)[:7]
        else:
            pat_str = "-"
        pat_str = pat_str.ljust(7)
        
        # 3. СОСТ (Состояние: Squat / Squeeze / Expansion)
        sost_emoji = ""
        if data.get("is_squat"):
            sost_emoji += "🔹"
        if data.get("is_squeeze"):
            sost_emoji += "⚪"
        elif data.get("is_expansion"):
            sost_emoji += "💥"
            
        if not sost_emoji:
            sost_emoji = " "
            
        table += f"{tf:<3} {time_val:<6} {sma_emoji}   {pat_str} {sost_emoji}\n"
        
    table += "</pre>"
    return header + table
