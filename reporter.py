from datetime import datetime, timedelta

def get_bar_close_time(tf: str, now: datetime) -> str:
    """
    Вычисляет время закрытия бара.
    Если бар закрывается в ближайшие 5 минут, показывает округленное время закрытия.
    Иначе показывает время последнего закрытого бара.
    """
    next_hour = (now + timedelta(minutes=5)).replace(minute=0, second=0, microsecond=0)
    
    if tf == "1h":
        return next_hour.strftime("%H:%M")
    
    elif tf == "4h":
        # 4H закрываются в 03:00, 07:00, 11:00, 15:00, 19:00, 23:00 MSK
        if next_hour.hour % 4 == 3:
            return next_hour.strftime("%H:%M")
        else:
            last_4h_hour = ((now.hour - 3) // 4) * 4 + 3
            last_closed = now.replace(hour=last_4h_hour, minute=0, second=0, microsecond=0)
            if last_closed > now:
                last_closed -= timedelta(days=1)
            return last_closed.strftime("%H:%M")
            
    elif tf == "1d":
        # 1D закрывается в 03:00 MSK
        if next_hour.hour == 3:
            return next_hour.strftime("%H:%M")
        else:
            return "03:00"
            
    elif tf == "1w":
        # 1W закрывается в понедельник в 03:00 MSK
        if now.weekday() == 0 and next_hour.hour == 3:
            return next_hour.strftime("%H:%M")
        else:
            return "03:00"
            
    return now.strftime("%H:%M")

def merge_signals(signals_list):
    """
    Группирует паттерны и состояния для одинаковых (symbol, time, tf) в одну строку.
    """
    grouped = {}
    for sig in signals_list:
        key = (sig['symbol'], sig['time'], sig['tf'])
        if key not in grouped:
            grouped[key] = {
                'symbol': sig['symbol'],
                'time': sig['time'],
                'tf': sig['tf'],
                'direction': sig.get('direction', '🔴'), # Направление закрытия относительно SMA(14)
                'patterns': [],
                'states': []
            }
        
        if sig.get('pattern'):
            grouped[key]['patterns'].append(sig['pattern'])
        if sig.get('state'):
            grouped[key]['states'].append(sig['state'])

    merged_rows = []
    for key, data in grouped.items():
        # Объединяем паттерны через '|' (Pin|Out)
        unique_pats = list(dict.fromkeys(data['patterns']))
        pat_str = "|".join(unique_pats) if unique_pats else ""
        
        # Объединяем символы состояний подряд (🟦🔷)
        unique_states = list(dict.fromkeys(data['states']))
        state_str = "".join(unique_states) if unique_states else ""
        
        merged_rows.append({
            'symbol': data['symbol'],
            'time': data['time'],
            'tf': data['tf'],
            'direction': data['direction'],
            'pat': pat_str,
            'state': state_str
        })
    return merged_rows

def build_report_text(signals: list, is_auto: bool = False, now: datetime = None) -> str:
    """
    Формирует итоговый текст отчета с моноширинной таблицей.
    """
    if now is None:
        now = datetime.now()
        
    date_str = now.strftime("%d.%m.%Y %H:%M")
    
    # Разделение заголовка для автоотчета и ручного запроса
    if is_auto:
        header = f"📊 АвтоОтчет ({date_str} MSK):"
    else:
        header = f"📊 Сводный отчёт ({date_str} MSK):"
        
    merged = merge_signals(signals)
    
    lines = ["АКТ | ВРЕМЯ | ТФ  | НАПР | ПАТ     | СОСТ", "----------------------------------------"]
    for row in merged:
        line = f"{row['symbol']:<3} | {row['time']:<5} | {row['tf']:<3} | {row['direction']}   | {row['pat']:<7} | {row['state']}"
        lines.append(line)
        
    table_text = "\n".join(lines)
    return f"{header}\n\n```text\n{table_text}\n```"
