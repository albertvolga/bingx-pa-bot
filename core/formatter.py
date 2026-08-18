from datetime import datetime, timedelta, timezone

MSK_TZ = timezone(timedelta(hours=3))

TF_SHORT_MAP = { # Для более короткого отображения ТФ в отчетах
    "1m": "1М", "5m": "5М", "15m": "15М", "30m": "30М",
    "1h": "1Ч", "4h": "4Ч", "1d": "1Д", "1w": "1Н"
}

def get_display_bar_time(dt_open: datetime, tf: str, is_auto: bool) -> str:
    """
    Вычисляет и форматирует время закрытия бара для отображения в отчете.
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

    # Для ручных отчетов всегда показываем время ОТКРЫТИЯ последнего закрытого бара
    # (поскольку fetch_bingx_candles возвращает время открытия)
    if not is_auto:
        return dt_open_msk.strftime("%H:%M") 

    # Для автоотчетов (is_auto=True) показываем ближайшее время ЗАКРЫТИЯ бара
    if tf == "1h":
        return (dt_open_msk + timedelta(hours=1)).strftime("%H:%M")
    elif tf == "4h":
        current_hour = dt_open_msk.hour
        # Определение следующего часа закрытия 4H бара (03, 07, 11, 15, 19, 23 MSK)
        next_close_hour = 0
        if current_hour < 3: next_close_hour = 3
        elif current_hour < 7: next_close_hour = 7
        elif current_hour < 11: next_close_hour = 11
        elif current_hour < 15: next_close_hour = 15
        elif current_hour < 19: next_close_hour = 19
        elif current_hour < 23: next_close_hour = 23
        else: next_close_hour = 3 # Для 23:xx текущей свечи, следующая закрывается в 03:00 след.дня

        return f"{next_close_hour:02d}:00"
    elif tf == "1d":
        return "03:00"
    elif tf == "1w":
        return "Пн 03:00" 
            
    return dt_open_msk.strftime("%H:%M")


def merge_signals(signals_list: list) -> list:
    """
    Группирует паттерны для одинаковых (symbol, time, tf) и добавляет информацию по индикаторам.
    """
    grouped = {}
    for sig in signals_list:
        key = (sig['symbol'], sig['tf'], sig.get('timestamp')) # Добавлено timestamp для уникальности бара
        
        if key not in grouped:
            grouped[key] = {
                'symbol': sig['symbol'],
                'tf': sig['tf'],
                'patterns': [],
                'is_auto': sig.get('is_auto', False),
                'dt_open_for_display': datetime.fromtimestamp(sig['timestamp'] / 1000, tz=timezone.utc),
                # Новые поля для индикаторов и состояния
                'direction_bb': sig.get('direction_bb', '⚪⚪⚪'), # 3 эмодзи по умолчанию
                'state_emoji': sig.get('state_emoji', ''), # Эмодзи состояния
            }
        
        if sig.get('pattern') and sig['pattern'] != "-":
            grouped[key]['patterns'].append(sig['pattern'])

    merged_rows = []
    for k, data in grouped.items():
        unique_pats = sorted(list(dict.fromkeys(data['patterns']))) # Сортировка паттернов
        pat_str = "/".join(unique_pats) if unique_pats else "-"
        
        merged_rows.append({
            'symbol': data['symbol'],
            'tf': data['tf'],
            'display_time': get_display_bar_time(data['dt_open_for_display'], data['tf'], data['is_auto']),
            'direction_bb': data['direction_bb'],
            'pattern': pat_str,
            'state_emoji': data['state_emoji'],
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
    TF_PRIORITY = {"1w": 4, "1d": 3, "4h": 2, "1h": 1, "15m": 0, "5m": -1, "1m": -2} # Расширен для будущих ТФ
    merged_signals.sort(key=lambda x: (x["symbol"], -TF_PRIORITY.get(x["tf"].lower(), 0)))

    table_header = f"{'АКТ':<4} | {'ВРЕМЯ':<5} | {'ТФ':<3} | {'НАПР'} | {'ПАТ':<7} | {'СОСТ'}\n"
    divider = "-" * 39 + "\n" # Увеличиваем разделитель под новые колонки
    
    lines = [f"<b>{header_title}</b>\n\n<pre>", table_header, divider]
    
    for r in merged_signals:
        symbol = str(r['symbol']).ljust(4)
        display_time = str(r['display_time']).ljust(5)
        tf_short = TF_SHORT_MAP.get(r['tf'].lower(), r['tf']).ljust(3) # Используем короткое имя ТФ
        direction_bb = str(r['direction_bb']) # Теперь это строка с эмодзи
        pattern = str(r['pattern']).ljust(7)
        state_emoji = str(r['state_emoji']).ljust(4) # Эмодзи состояния
        
        row_str = f"{symbol} | {display_time} | {tf_short} | {direction_bb} | {pattern} | {state_emoji}\n"
        lines.append(row_str)
        
    lines.append("</pre>")
    return "".join(lines)

def format_alerts_table(alerts_list: list) -> tuple[str, list]:
    """
    Формирует итоговый текст таблицы алертов.
    Возвращает текст и список кнопок.
    """
    if not alerts_list:
        return "📋 У вас пока нет активных алертов.", []
    
    text = "<b>📌 Ваши активные алерты:</b>\n\n<pre>"
    text += f"{'ID':<4} | {'Монета':<6} | {'Уровень':<10} | {'Примечание'}\n"
    text += "-" * 42 + "\n" # Увеличиваем разделитель под 42 символа
    
    buttons = []
    for a in alerts_list:
        aid = a['id']
        sym = a['symbol']
        price = f"{a['target_price']:.2f}" if a['target_price'] is not None else "---"
        note = a['note'] or "Без примечания"
            
        text += f"#{aid:<3} | {sym:<6} | {price:<10} | {note}\n"
        buttons.append({"text": f"❌ #{aid}", "callback_data": f"del_alert_{aid}"})
    
    text += "</pre>"
    return text, buttons
