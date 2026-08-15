import asyncio
import logging
from datetime import datetime, timezone, timedelta
from core.fetcher import fetch_klines, get_all_usdt_pairs
from core.patterns import analyze_patterns
from core.formatter import format_table_report

MSK_TZ = timezone(timedelta(hours=3))

async def scan_and_notify(bot, chat_id: int, target_tf: str = None):
    if not chat_id:
        logging.warning("Scheduler: CHAT_ID не установлен, авто-уведомление пропущено.")
        return
    try:
        symbols = await get_all_usdt_pairs()
        all_signals = []
        tfs_to_scan = [target_tf] if target_tf else ["1h", "4h", "1d", "1w"]

        for tf in tfs_to_scan:
            for sym in symbols:
                df = await fetch_klines(sym, tf, limit=30)
                if df is not None and len(df) >= 3:
                    pats = analyze_patterns(df)
                    for p in pats:
                        curr = df.iloc[-2]
                        direction = "bull" if curr['close'] >= curr['open'] else "bear"
                        all_signals.append({
                            "symbol": sym,
                            "tf": tf,
                            "pattern": p,
                            "direction": direction,
                            "is_forming": False
                        })

        now_msk = datetime.now(MSK_TZ)
        title = f"Авто-отчёт {target_tf.upper()}" if target_tf else "Авто-отчёт"
        report_text = format_table_report(all_signals, report_title=title, now_dt=now_msk, tf_type=target_tf or "all")

        if all_signals:
            await bot.send_message(chat_id=chat_id, text=report_text, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Ошибка в авто-сканере ({target_tf}): {e}")

async def start_scheduler(bot, chat_id: int):
    logging.info("Планировщик авто-отчётов запущен.")
    while True:
        now = datetime.now(MSK_TZ)
        if now.minute == 55:
            # Каждый час в :55 отправляем 1h
            await scan_and_notify(bot, chat_id, target_tf="1h")
            
            # 4h свечи закрываются в 03:00, 07:00, 11:00, 15:00, 19:00, 23:00 MSK
            # В :55 отчёт уходит в 02:55, 06:55, 10:55, 14:55, 18:55, 22:55
            if now.hour in (2, 6, 10, 14, 18, 22):
                await scan_and_notify(bot, chat_id, target_tf="4h")
            
            # Дневная свеча закрывается в 03:00 MSK -> отчёт в 02:55 MSK
            if now.hour == 2:
                await scan_and_notify(bot, chat_id, target_tf="1d")
                
                # Недельный отчёт: воскресенье (weekday == 6) в 02:55 MSK (перед закрытием недели в 03:00 ПН)
                if now.weekday() == 6:
                    await scan_and_notify(bot, chat_id, target_tf="1w")
            
            # Спим 60 секунд, чтобы исключить повторное срабатывание в течение той же 55-й минуты
            await asyncio.sleep(60)
        
        await asyncio.sleep(20)
