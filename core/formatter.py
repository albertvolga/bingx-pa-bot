from datetime import datetime, timezone, timedelta
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

MSK_TZ = timezone(timedelta(hours=3))

def build_compact_keyboard(buttons: list, row_width: int = 4) -> InlineKeyboardMarkup:
    keyboard = []
    row = []
    for btn in buttons:
        row.append(btn)
        if len(row) >= row_width:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def format_alerts_table(chat_id: int = None) -> tuple:
    return "🔔 <b>Список алертов пуст.</b>", []

def get_bar_close_time(tf: str, bar_time_ms: int = None, now_dt: datetime = None) -> str:
    """Возвращает время закрытия свечи по МСК без ошибочного сдвига."""
    if bar_time_ms:
        if bar_time_ms < 10000000000:
            bar_time_ms *= 1000
        dt = datetime.fromtimestamp(bar_time_ms / 1000, tz=timezone.utc) + timedelta(hours=3)
        return dt.strftime("%H:%M")
    
    if not now_dt:
        now_dt = datetime.now(MSK_TZ)
        
    tf_lower = tf.lower()
    if tf_lower == "15m":
        m = ((now_dt.minute // 15) + 1) * 15
        h = now_dt.hour
        if m >= 60:
            h = (h + 1) % 24
            m = 0
        return f"{h:02d}:{m:02d}"
    elif tf_lower == "1h":
        return f"{now_dt.hour:02d}:00"
    elif tf_lower == "4h":
        current_hour = now_dt.hour
        for target_h in [3, 7, 11, 15, 19, 23]:
            if current_hour <= target_h:
                return f"{target_h:02d}:00"
        return "03:00"
    elif tf_lower in ["1d", "d1", "1w", "w1"]:
        return "03:00"
        
    return now_dt.strftime("%H:%M")

def format_table_report(raw_signals: list, report_title: str = "Отчёт", now_dt: datetime = None, tf_type: str = None) -> str:
    # Исключаем дублирование даты и скобок в заголовке
    if "МСК" in report_title or "MSK" in report_title or "(" in report_title:
        header = f"📊 <b>{report_title}</b>\n\n"
    else:
        if not now_dt:
            now_dt = datetime.now(MSK_TZ)
        header = f"📊 <b>{report_title} ({now_dt.strftime('%d.%m.%y %H:%M')} МСК)</b>\n\n"
        
    if not raw_signals:
        return header + "<i>Сигналов по заданным критериям не найдено.</i>"
        
    grouped = {}
    for sig in raw_signals:
        sym = sig.get("symbol", "")
        tf = sig.get("tf", "1h")
        bar_time = sig.get("bar_time", 0)
        
        key = (sym, tf, bar_time)
        if key not in grouped:
            grouped[key] = {
                "symbol": sym,
                "tf": tf,
                "bar_time": bar_time,
                "direction": sig.get("direction", "bull"),
                "patterns": [],
                "states": []
            }
        
        pat_raw = sig.get("pattern", "")
        if pat_raw and pat_raw not in grouped[key]["patterns"]:
            grouped[key]["patterns"].append(pat_raw)
        
        if sig.get("is_squat") and "🔹" not in grouped[key]["states"]:
            grouped[key]["states"].append("🔹")
        if sig.get("is_squeeze") and "☀️" not in grouped[key]["states"]:
            grouped[key]["states"].append("☀️")
        if sig.get("is_expansion") and "💥" not in grouped[key]["states"]:
            grouped[key]["states"].append("💥")

    sorted_items = sorted(
        grouped.values(),
        key=lambda x: (x["symbol"], -int(x["bar_time"] or 0))
    )

    lines = []
    lines.append("<pre>")
    lines.append("АКТ | ВРЕМЯ | ТФ  |НАПР| ПАТ    | СОСТ")
    lines.append("------------------------------------")
    
    tf_display_map = {"15M": "15м", "1H": "1Ч", "4H": "4Ч", "1D": "1Д", "D1": "1Д", "1W": "1Н", "W1": "1Н"}
    
    rows_count = 0
    for data in sorted_items:
        if not data["patterns"] and not data["states"]:
            continue
            
        sym = data["symbol"].replace("-USDT", "").replace("USDT", "")[:3].ljust(3)
        raw_tf = data["tf"].upper()
        sig_tf = tf_display_map.get(raw_tf, raw_tf).rjust(3)
        time_str = get_bar_close_time(data["tf"], bar_time_ms=data.get("bar_time"), now_dt=now_dt)
        dir_icon = "🟡" if data["direction"] == "bull" else "🔴"
        
        pat_str = "/".join(data["patterns"]) if data["patterns"] else "-"
        pat_str = pat_str[:7].ljust(7)
        state_str = "".join(data["states"]) if data["states"] else "  "
        
        lines.append(f"{sym} | {time_str} | {sig_tf} | {dir_icon} | {pat_str} | {state_str}")
        rows_count += 1
        
    lines.append("</pre>")
    
    if rows_count == 0:
        return header + "<i>Сигналов по заданным критериям не найдено.</i>"
        
    return header + "\n".join(lines)
