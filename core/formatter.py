from datetime import datetime, timedelta, timezone

MSK_TZ = timezone(timedelta(hours=3))

def get_display_bar_time(dt_open: datetime, tf: str, is_auto: bool) -> str:
    """
    Вычисляет и форматирует время закрытия бара для отображения.
    :param dt_open: Время ОТКРЫТИЯ свечи (в UTC).
    :param tf: Таймфрейм ('1h', '4h', '1d', '1w').
    :param is_auto: True для автоотчета (5 мин до закрытия), False для ручного (факт закрытия).
    :return: Отформатированная строка времени.
    """
    if dt_open is None:
        return "Н/Д"
    if dt_open.tzinfo is None:
        dt_open = dt_open.replace(tzinfo=timezone.utc)
    
    dt_open_msk = dt_open.astimezone(MSK_TZ)

    if is_auto:
        # Для автоотчетов показываем ближайшее время закрытия бара
        if tf == "1h":
            return (dt_open_msk + timedelta(hours=1)).strftime("%H:%M")
        elif tf == "4h":
            # 4H закрываются в 03, 07, 11, 15, 19, 23 MSK
            # Если текущая свеча открылась в 14:00, закроется в 15:00. 
            # Нам нужно отобразить время закрытия текущей формирующейся свечи.
            current_hour = dt_open_msk.hour
            next_close_hour = 0
            
            if current_hour < 3: next_close_hour = 3
            elif current_hour < 7: next_close_hour = 7
            elif current_hour < 11: next_close_hour = 11
            elif current_hour < 15: next_close_hour = 15
            elif current_hour < 19: next_close_hour = 19
            elif current_hour < 23: next_close_hour = 23
            else: next_close_hour = 3 # Для 23:xx следующая 03:00

            return f"{next_close_hour:02d}:00"
        elif tf == "1d":
            return "03:00"
        elif tf == "1w":
            return "Пн 03:00" 
        
    else: # Для ручных отчетов показываем время ОТКРЫТИЯ бара (т.к. fetch_bingx_candles возвращает время открытия)
        # ИЛИ время закрытия, если оно явно передано.
        # В данном случае, dt_open - это время открытия последней закрытой свечи.
        return dt_open_msk.strftime("%H:%M") # "Время открытия" последнего закрытого бара
            
    return dt_open_msk.strftime("%H:%M")


def merge_signals(signals_list):
    """
    Группирует паттерны для одинаковых (symbol, time, tf) в одну строку.
    """
    grouped = {}
    for sig in signals_list:
        # Ключ для группировки теперь включает 'is_auto' для корректного отображения времени
        # Используем символ и таймфрейм для ключа
        key = (sig['symbol'], sig['tf'], sig.get('is_auto', False)) 
        
        if key not in grouped:
            grouped[key] = {
                'symbol': sig['symbol'],
                'tf': sig['tf'],
                'direction': sig.get('direction', '⚪'), # Направление
                'patterns': [],
                'is_auto': sig.get('is_auto', False),
                'dt_open_for_display': datetime.fromtimestamp(sig['timestamp'] / 1000, tz=timezone.utc) if 'timestamp' in sig and sig['timestamp'] else None,
            }
        
        if sig.get('pattern') and sig['pattern'] != "-":
            grouped[key]['patterns'].append(sig['pattern'])

    merged_rows = []
    for k, data in grouped.items():
        unique_pats = list(dict.fromkeys(data['patterns']))
        pat_str = "/".join(unique_pats) if unique_pats else "-"
        
        merged_rows.append({
            'symbol': data['symbol'],
            'tf': data['tf'],
            'display_time': get_display_bar_time(data['dt_open_for_display'], data['tf'], data['is_auto']),
            'direction': data['direction'],
            'pattern': pat_str,
        })
    return merged_rows

def format_report(signals: list, is_auto: bool = False, now_dt: datetime = None) -> str:
    """
    Формирует итоговый текст отчета с моноширинной таблицей.
    Поддерживает как автоотчеты (is_auto=True), так и ручные сканы.
    """
    if now_dt is None:
        now_dt = datetime.now(MSK_TZ)
        
    date_str = now_dt.strftime("%d.%m.%Y %H:%M")
    
    if is_auto:
        header_title = f"📊 АвтоОтчёт ({date_str} МСК):"
    else:
        header_title = f"📊 Отчёт о паттернах ({date_str} МСК):"
        
    if not signals:
        return f"<b>{header_title}</b>\n\n✅ Интересных паттернов не найдено."

    merged_signals = merge_signals(signals)
    
    # Сортировка перед выводом (по символу, потом по ТФ)
    TF_PRIORITY = {"1w": 4, "1d": 3, "4h": 2, "1h": 1, "15m": 0} # Локальная копия для сортировки
    merged_signals.sort(key=lambda x: (x["symbol"], -TF_PRIORITY.get(x["tf"].lower(), 0)))

    table_header = f"{'АКТ':<4} | {'ВРЕМЯ':<5} | {'ТФ':<3} | {'НАПР'} | {'ПАТ':<7}\n"
    divider = "-" * 30 + "\n"
    
    lines = [f"<b>{header_title}</b>\n\n<pre>", table_header, divider]
    
    for r in merged_signals:
        symbol = str(r['symbol']).ljust(4)
        display_time = str(r['display_time']).ljust(5)
        tf = str(r['tf']).ljust(2)
        direction = str(r['direction'])
        pattern = str(r['pattern']).ljust(7)
        
        row_str = f"{symbol} | {display_time} | {tf} | {direction}   | {pattern}\n"
        lines.append(row_str)
        
    lines.append("</pre>")
    return "".join(lines)
