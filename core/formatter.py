import logging
from datetime import datetime, timezone, timedelta

MSK_TZ = timezone(timedelta(hours=3))

TF_SHORT_MAP = {
    '1h': '1H', '4h': '4H', '1d': '1D', '1w': '1W',
    '1H': '1H', '4H': '4H', '1D': '1D', '1W': '1W',
}

TF_ORDER = {'1w': 1, '1d': 2, '4h': 3, '1h': 4, '1W': 1, '1D': 2, '4H': 3, '1H': 4}

def clean_symbol(symbol: str) -> str:
    return symbol.replace("-USDT", "").replace("USDT", "")

def get_display_bar_time(dt_open, tf: str, is_auto: bool) -> str:
    """
    Возвращает время ЗАКРЫТИЯ бара в формате ЧЧ:ММ по МСК.
    Игнорирует реальное время свечи, использует стандартное расписание биржи.
    """
    try:
        if not isinstance(dt_open, datetime):
            if isinstance(dt_open, (int, float)):
                dt_open = datetime.fromtimestamp(dt_open / 1000, tz=timezone.utc)
            else:
                return "--:--"
        
        # Конвертируем дату в МСК только для получения числа (день), 
        # но время будем задавать вручную.
        dt_msk = dt_open.astimezone(MSK_TZ)
        tf_clean = str(tf).lower()
        
        # Расписание закрытия свечей по МСК (время начала СЛЕДУЮЩЕЙ свечи)
        # Но в отчетах мы обычно пишем время, КОГДА свеча закрылась (конец интервала).
        # Для 1H: закрытие в 00:00, 01:00 ... 23:00.
        # Для 4H: закрытие в 03:00, 07:00, 11:00, 15:00, 19:00, 23:00.
        # Для 1D: закрытие в 03:00 (следующего дня).
        # Для 1W: закрытие в 03:00 (понедельника следующей недели).
        
        hour = dt_msk.hour
        
        if tf_clean == '1h':
            # Часовой бар закрывается в конце часа. 
            # Если сейчас 14:35, последний закрытый бар был в 14:00 (закрылся в 15:00? Нет, бар 14-15 закрывается в 15:00)
            # Обычно в таблицах пишут время ЗАВЕРШЕНИЯ формирования.
            # Бар, который сформировался к текущему моменту (предыдущий), закрылся в текущий полный час.
            # Пример: сейчас 14:35. Закрытый бар 13:00-14:00. Время закрытия 14:00.
            return f"{hour:02d}:00"
            
        elif tf_clean == '4h':
            # 4-часовые бары закрываются в 03, 07, 11, 15, 19, 23.
            # Логика: находим ближайшее прошлое время закрытия.
            # Часы закрытия: [3, 7, 11, 15, 19, 23]
            close_hours = [3, 7, 11, 15, 19, 23]
            
            # Находим подходящий час. Если сейчас 18:00, то последний закрытый был в 15:00 (следующий в 19:00).
            # Если сейчас 19:05, последний закрытый в 19:00.
            last_close_h = close_hours[0]
            for h in close_hours:
                if h <= hour:
                    last_close_h = h
                else:
                    break
            
            # Корректировка: если сейчас например 02:59, то последний закрытый был вчера в 23:00.
            # Но наша функция получает dt_open самой свечи. 
            # Если нам передали свечу, которая уже закрылась, её время закрытия фиксировано.
            # Проще: взять час свечи и округлить до сетки 4H.
            # Но надежнее всего просто вернуть строку из списка, соответствующую периоду.
            # Давайте сделаем так: если час свечи попадает в интервал, возвращаем время конца этого интервала.
            
            # Интервалы: 23-03, 03-07, 07-11, 11-15, 15-19, 19-23.
            # Свеча с открытием в 15:00 закроется в 19:00.
            # Свеча с открытием в 11:00 закроется в 15:00.
            
            # Маппинг открытия -> закрытие (МСК)
            # Открытия баров: 23, 03, 07, 11, 15, 19.
            # Закрытия баров: 03, 07, 11, 15, 19, 23.
            
            mapping = {23: "03:00", 3: "07:00", 7: "11:00", 11: "15:00", 15: "19:00", 19: "23:00"}
            
            # Находим ближайшее открытие в прошлом
            open_hours = [23, 3, 7, 11, 15, 19]
            current_open = open_hours[0]
            for h in open_hours:
                if h <= hour:
                    current_open = h
                else:
                    break
            
            # Проверка: если час большой (например 22), а маппинга нет для 22 как ключа, 
            # значит это бар, открывшийся в 19:00.
            # Нам нужно найти ключ, который <= hour.
            # В списке [23, 3, 7...], если hour=18, то max(h <= 18) это 15. Значит бар открыт в 15, закроется в 19.
            # Если hour=22, max(h <= 22) это 19. Бар открыт в 19, закроется в 23.
            # Если hour=2, max(h <= 2) это 23 (вчера). Бар открыт в 23, закроется в 03.
            
            # Реализуем поиск:
            best_open = 23 # default yesterday
            for h in [3, 7, 11, 15, 19, 23]:
                if h <= hour:
                    best_open = h
                else:
                    break # так как список отсортирован
            
            return mapping.get(best_open, f"{hour:02d}:00")

        elif tf_clean == '1d':
            return "03:00"
            
        elif tf_clean == '1w':
            return "03:00"
            
        return f"{hour:02d}:00"
        
    except Exception:
        return "--:--"
def merge_signals(signals_list: list) -> list:
    grouped = {}
    
    if not signals_list:
        return []

    for sig in signals_list:
        # Безопасное извлечение данных
        symbol = sig.get('symbol', 'UNK')
        tf = str(sig.get('tf', '1h')).lower()
        timestamp = sig.get('timestamp')
        
        key = (symbol, tf, timestamp)
        
        if key not in grouped:
            # Обработка времени
            ts = timestamp
            if hasattr(ts, 'to_pydatetime'):
                dt_val = ts.to_pydatetime().replace(tzinfo=timezone.utc)
            elif isinstance(ts, (int, float)):
                dt_val = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            elif isinstance(ts, datetime):
                dt_val = ts
            else:
                dt_val = datetime.now(MSK_TZ)

            grouped[key] = {
                'symbol': symbol,
                'tf': tf,
                'patterns': [],
                'bb_breakthroughs': [],
                'is_auto': sig.get('is_auto', False),
                'dt_open_for_display': dt_val,
                'direction_bb': sig.get('direction_bb') or '⚪⚪⚪',
                'state_emoji': sig.get('state_emoji') or '',
            }
        
        # Добавляем паттерн, если он есть и не "-"
        pat = sig.get('pattern')
        if pat and pat != "-":
            grouped[key]['patterns'].append(pat)

        bb = sig.get('bb_breakthrough')
        if bb and bb != "-":
            grouped[key]['bb_breakthroughs'].append(bb)

    merged_rows = []
    for k, data in grouped.items():
        unique_pats = sorted(list(dict.fromkeys(data['patterns'])))
        pat_str = "/".join(unique_pats) if unique_pats else "-"

        unique_bbs = sorted(list(dict.fromkeys(data['bb_breakthroughs'])))
        bb_str = "/".join(unique_bbs) if unique_bbs else ""
        
        tf_display = TF_SHORT_MAP.get(data['tf'], data['tf'].upper())

        merged_rows.append({
            'symbol': clean_symbol(data['symbol']),
            'tf': tf_display,
            'display_time': get_display_bar_time(data['dt_open_for_display'], data['tf'], data['is_auto']),
            'direction_bb': data['direction_bb'],
            'pattern': pat_str,
            'state_emoji': data['state_emoji'],
            'bb_breakthrough': bb_str,
        })

    # Сортировка
    merged_rows.sort(key=lambda x: (x['symbol'], TF_ORDER.get(x['tf'].lower(), 99)))
    return merged_rows

def format_report(signals: list, is_auto: bool = False, now_dt: datetime = None) -> str:
    if now_dt is None:
        now_dt = datetime.now(MSK_TZ)
        
    date_str = now_dt.strftime("%d.%m.%Y %H:%M")
    header_title = f"📊 АвтоОтчёт ({date_str} МСК):" if is_auto else f"📊 Отчёт о паттернах ({date_str} МСК):"
    
    # Если сигналов нет - сразу возвращаем
    if not signals or len(signals) == 0:
        return f"<b>{header_title}</b>\n\n✅ Интересных паттернов не найдено."

    # Мерджим сигналы
    merged_signals = merge_signals(signals)
    
    # Если после мерджа стало пусто (были дубли или ошибки)
    if not merged_signals:
        return f"<b>{header_title}</b>\n\n✅ Интересных паттернов не найдено."

    table_lines = ["АКТ  | ВРЕМЯ | ТФ | НАПР   | ПАТ     | СОСТ| ББ", "--------------------------------------------"]

    for row in merged_signals:
        sym = f"{row['symbol']:<4}"
        tm = f"{row['display_time']:<5}"
        tf = f"{row['tf']:<2}"
        dir_bb = f"{row['direction_bb']}"
        pat = f"{row['pattern']:<7}"
        st = f"{row['state_emoji']:<3}" if row['state_emoji'] else "   "
        bb = f"{row['bb_breakthrough']}"

        line = f"{sym} | {tm} | {tf} | {dir_bb} | {pat} | {st} | {bb}"
        table_lines.append(line)

    table_text = "\n".join(table_lines)
    return f"<b>{header_title}</b>\n\n<code>{table_text}</code>"

def format_alerts_table(alerts: list) -> str:
    if not alerts:
        return "У вас нет активных алертов."
    
    lines = ["🔔 <b>Активные алерты:</b>\n", "<code>АКТ  | ЦЕНА     | ТИП</b>"]
    lines.append("-----------------------")
    for a in alerts:
        sym = clean_symbol(a.get('symbol', ''))
        price = f"{a.get('target_price', 0):<8}"
        condition = a.get('condition', '>=')
        lines.append(f"{sym:<4} | {price} | {condition}")
    
    return "\n".join(lines) + "</code>"
