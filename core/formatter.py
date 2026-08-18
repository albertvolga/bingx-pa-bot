def format_table_report(timestamp_str, report_rows):
    """
    Формирует моноширинный табличный автоотчет без лишних меток и столбца СОСТ
    """
    header = f"📊 АвтоОтчёт ({timestamp_str})\n\n"
    table_header = "АКТ  | ВРЕМЯ | ТФ | НАПР | ПАТ  \n"
    divider = "--------------------------------\n"
    
    lines = [header, "```\n", table_header, divider]
    
    for r in report_rows:
        # Безопасное извлечение полей с поддержкой разных форматов словаря
        asset = str(r.get("asset", r.get("symbol", ""))).ljust(4)
        time_val = str(r.get("time", r.get("timeframe", ""))).ljust(5)
        tf_val = str(r.get("tf", "")).ljust(2)
        direction = str(r.get("dir", r.get("direction", "🔴")))
        pattern = str(r.get("pat", r.get("pattern", "-"))).ljust(4)
        
        row_str = f"{asset} | {time_val} | {tf_val} | {direction}   | {pattern}\n"
        lines.append(row_str)
        
    lines.append("```")
    return "".join(lines)

# Алиас для обратной совместимости, если где-то используется альтернативное имя
format_auto_report = format_table_report
