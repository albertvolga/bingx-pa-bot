import logging
from datetime import datetime, timezone, timedelta

MSK_TZ = timezone(timedelta(hours=3))

TF_SHORT_MAP = {
    '1h': '1h',
    '4h': '4h',
    '1d': '1d',
    '1w': '1w',
    '1H': '1h',
    '4H': '4h',
    '1D': '1d',
    '1W': '1w',
    '14': '1h'
}

def clean_symbol(symbol: str) -> str:
    """Убирает суффиксы и тире из символа для лаконичного вывода."""
    return symbol.replace("-USDT", "").replace("USDT", "")

def get_display_bar_time(dt_open: datetime, tf: str, is_auto: bool) -> str:
    """
    Возвращает форматированное время закрытия/открытия бара в зависимости от типа скана.
    """
    if not isinstance(dt_open, datetime):
        return "--:--"

    dt_open_msk = dt_open.astimezone(MSK_TZ)

    tf_clean = str(tf).lower()
    tf_offsets = {
        '1h': timedelta(hours=1),
        '4h': timedelta(hours=4),
        '1d': timedelta(days=1),
        '1w': timedelta(weeks=1),
    }

    if is_auto:
        offset = tf_offsets.get(tf_clean, timedelta(hours=1))
        dt_close_msk = dt_open_msk + offset
        return dt_close_msk.strftime("%H:%M")
    else:
        return dt_open_msk.strftime("%H:%M")

def merge_signals(signals_list: list) -> list:
    """
    Группирует паттерны для одинаковых (symbol, time, tf) и добавляет информацию по индикаторам.
    """
    grouped = {}
    for sig in signals_list:
        key = (sig['symbol'], sig['tf'], sig.get('timestamp'))
        
        if key not in grouped:
            ts = sig.get('timestamp')
            if hasattr(ts, 'to_pydatetime'):
                dt_val = ts.to_pydatetime().replace(tzinfo=timezone.utc)
            elif isinstance(ts, (int, float)):
                dt_val = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            else:
                dt_val = ts

            grouped[key] = {
                'symbol': sig['symbol'],
                'tf': sig['tf'],
                'patterns': [],
                'bb_breakthroughs': [],
                'is_auto': sig.get('is_auto', False),
                'dt_open_for_display': dt_val,
                'direction_bb': sig.get('direction_bb', '⚪⚪⚪'),
                'state_emoji': sig.get('state_emoji', ''),
            }
        
        if sig.get('pattern') and sig['pattern'] != "-":
            grouped[key]['patterns'].append(sig['pattern'])

        if sig.get('bb_breakthrough') and sig['bb_breakthrough'] != "-":
            grouped[key]['bb_breakthroughs'].append(sig['bb_breakthrough'])

    merged_rows = []
    for k, data in grouped.items():
        unique_pats = sorted(list(dict.fromkeys(data['patterns'])))
        pat_str = "/".join(unique_pats) if unique_pats else "-"

        unique_bbs = sorted(list(dict.fromkeys(data['bb_breakthroughs'])))
        bb_str = "/".join(unique_bbs) if unique_bbs else ""
        
        tf_display = TF_SHORT_MAP.get(str(data['tf']), str(data['tf']))

        merged_rows.append({
            'symbol': clean_symbol(data['symbol']),
            'tf': tf_display,
            'display_time': get_display_bar_time(data['dt_open_for_display'], data['tf'], data['is_auto']),
            'direction_bb': data['direction_bb'],
            'pattern': pat_str,
            'state_emoji': data['state_emoji'],
            'bb_breakthrough': bb_str,
        })
    return merged_rows

def format_report(signals: list, is_auto: bool = False, now_dt: datetime = None) -> str:
    """
    Формирует итоговый текст отчета с моноширинной таблицей.
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

    table_lines = ["АКТ  | ВРЕМЯ | ТФ | НАПР | ПАТ     | СОСТ | ББ", "------------------------------------------"]

    for row in merged_signals:
        sym = f"{row['symbol']:<4}"
        tm = f"{row['display_time']:<5}"
        tf = f"{row['tf']:<2}"
        dir_bb = f"{row['direction_bb']}"
        pat = f"{row['pattern']:<7}"
        st = f"{row['state_emoji']:<4}"
        bb = f"{row['bb_breakthrough']}"

        line = f"{sym} | {tm} | {tf} | {dir_bb} | {pat} | {st} | {bb}"
        table_lines.append(line)

    table_text = "\n".join(table_lines)
    return f"<b>{header_title}</b>\n\n<code>{table_text}</code>"

def format_alerts_table(alerts: list) -> str:
    """
    Форматирует список алертов для ИИ-обработчика/команд.
    """
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
