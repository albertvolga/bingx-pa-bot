from datetime import datetime, timezone, timedelta

MSK_TZ = timezone(timedelta(hours=3))

def get_bar_close_time(tf: str, now_dt: datetime) -> str:
    if tf == "15m":
        m = (now_dt.minute // 15) * 15
        return f"{now_dt.hour:02d}:{m:02d}"
    elif tf == "1h":
        return f"{now_dt.hour:02d}:00"
    elif tf == "4h":
        current_hour = now_dt.hour
        for target_h in [23, 19, 15, 11, 7, 3]:
            if current_hour >= target_h:
                return f"{target_h:02d}:00"
        return "23:00"
    elif tf in ["1d", "d1", "1w", "w1"]:
        return "03:00"
    return now_dt.strftime("%H:%M")

def format_table_report(raw_signals: list, report_title: str = "Отчёт", now_dt: datetime = None, tf_type: str = None) -> str:
    if not now_dt:
        now_dt = datetime.now(MSK_TZ)
        
    header = f"📊 <b>{report_title} ({now_dt.strftime('%d.%m %H:%M')} MSK):</b>\n\n"
    if not raw_signals:
        return header + "<i>Сигналов по заданным критериям не найдено.</i>"
        
    grouped = {}
    for sig in raw_signals:
        sym = sig.get("symbol", "")
        tf = sig.get("tf", "1h")
        key = (sym, tf)
        if key not in grouped:
            grouped[key] = {
                "symbol": sym,
                "tf": tf,
                "direction": sig.get("direction", "bull"),
                "patterns": [],
                "states": [],
                "is_forming": sig.get("is_forming", False)
            }
        
        pat_raw = sig.get("pattern", "")
        if pat_raw == "Squat":
            if "🔹" not in grouped[key]["states"]:
                grouped[key]["states"].append("🔹")
        else:
            pat_map = {
                "Pin Bar": "Pin", 
                "Outside Bar": "Out", 
                "PPR": "PPR", 
                "Fakey": "Fak", 
                "Inside Bar": "Ins"
            }
            short_pat = pat_map.get(pat_raw, pat_raw[:3])
            if short_pat not in grouped[key]["patterns"]:
                grouped[key]["patterns"].append(short_pat)
        
        if sig.get("is_squeeze") and "☀️" not in grouped[key]["states"]:
            grouped[key]["states"].append("☀️")
        if sig.get("is_expansion") and "💥" not in grouped[key]["states"]:
            grouped[key]["states"].append("💥")

    lines = []
    lines.append("<pre>")
    lines.append("АКТ  | ВРЕМЯ | ТФ  |НАПР| ПАТ    | СОСТ ")
    lines.append("------------------------------------")
    
    tf_display_map = {"15M": "15м", "1H": "1Ч", "4H": "4Ч", "1D": "1Д", "D1": "1Д", "1W": "1Н", "W1": "1Н"}
    
    for key, data in grouped.items():
        sym = data["symbol"].replace("-USDT", "").replace("USDT", "")[:4].ljust(4)
        
        raw_tf = data["tf"].upper()
        sig_tf = tf_display_map.get(raw_tf, raw_tf).rjust(3)
        
        time_str = get_bar_close_time(data["tf"], now_dt)
        
        # Яркие желтые кружки для удобства зрения
        dir_icon = "🟡" if data["direction"] == "bull" else "🔴"
        
        pat_str = "|".join(data["patterns"]) if data["patterns"] else ""
        pat_str = pat_str[:7].ljust(7)
        
        if data["is_forming"] and "🟦" not in data["states"]:
            data["states"].append("🟦")
            
        state_str = "".join(data["states"]) if data["states"] else "  "
        
        lines.append(f"{sym} | {time_str} | {sig_tf} | {dir_icon} | {pat_str} | {state_str}")
        
    lines.append("</pre>")
    return header + "\n".join(lines)
