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
            await scan_and_notify(bot, chat_id, target_tf="1h")
            if now.hour % 4 == 3:
                await scan_and_notify(bot, chat_id, target_tf="4h")
            if now.hour == 3:
                await scan_and_notify(bot, chat_id, target_tf="1d")
            await asyncio.sleep(60)
        await asyncio.sleep(20)
