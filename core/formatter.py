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
    try:
        if not isinstance(dt_open, datetime):
            if isinstance(dt_open, (int, float)):
                dt_open = datetime.fromtimestamp(dt_open / 1000, tz=timezone.utc)
            else:
                return "--:--"
        
        # Переводим в MSK
        dt_open_msk = dt_open.astimezone(MSK_TZ)
        tf_clean = str(tf).lower()
        
        # Длительность свечи для расчета времени ЗАКРЫТИЯ
        delta_map = {
            '1h': timedelta(hours=1),
            '4h': timedelta(hours=4),
            '1d': timedelta(days=1),
            '1w': timedelta(weeks=1)
        }
        delta = delta_map.get(tf_clean, timedelta(hours=1))
        
        # Время закрытия = время открытия + длительность
        dt_close_msk = dt_open_msk + delta
        
        # Форматируем только часы и минуты (без даты)
        return dt_close_msk.strftime("%H:%M")
        
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
