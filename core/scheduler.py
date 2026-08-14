import asyncio
from datetime import datetime, timezone, timedelta
from aiogram import Bot
from core.database import get_connection, delete_alert
from core.fetcher import fetch_klines, get_all_usdt_pairs
from core.patterns import analyze_patterns
from core.formatter import format_table_report

MSK_TZ = timezone(timedelta(hours=3))

async def start_scheduler(bot: Bot):
    """Фоновый цикл проверки алертов и отправки авто-отчетов"""
    last_auto_report_time = None

    while True:
        try:
            now_msk = datetime.now(MSK_TZ)

            # 1. ПРОВЕРКА АВТО-ОТЧЕТОВ ЗА 5 МИНУТ ДО ЗАКРЫТИЯ СВЕЧЕЙ (:55)
            if now_msk.minute == 55 and (last_auto_report_time is None or (now_msk - last_auto_report_time).total_seconds() > 180):
                last_auto_report_time = now_msk
                
                # Определяем таймфреймы для отчета
                tfs_to_send = ["1h"]
                
                # За 5 минут до закрытия 4H (02:55, 06:55, 10:55, 14:55, 18:55, 22:55)
                if now_msk.hour % 4 == 2:
                    tfs_to_send.append("4h")
                
                # За 5 минут до закрытия дня (02:55 MSK)
                if now_msk.hour == 2:
                    tfs_to_send.append("1d")
                    # Если понедельник 02:55 MSK — закрывается и недельная свеча
                    if now_msk.weekday() == 0:
                        tfs_to_send.append("1w")

                # Формируем и отправляем отчеты
                symbols = await get_all_usdt_pairs()
                all_signals = []

                for tf in tfs_to_send:
                    for sym in symbols:
                        df = await fetch_klines(sym, tf, limit=30)
                        if df is not None and len(df) >= 3:
                            pats = analyze_patterns(df)
                            for p in pats:
                                curr = df.iloc[-2]
                                direction = "bull" if curr['close'] >= curr['open'] else "bear"
                                all_signals.append({
                                    "symbol": sym.replace("-USDT", ""),
                                    "tf": tf,
                                    "pattern": p,
                                    "direction": direction,
                                    "is_forming": False
                                })

                tf_title = " + ".join([t.upper() for t in tfs_to_send])
                report_text = format_table_report(all_signals, report_title=f"Авто-отчёт {tf_title}", now_dt=now_msk, tf_type="all")
                
                # Отправляем админу/активному чату со ЗВУКОМ
                with get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT DISTINCT chat_id FROM alerts WHERE chat_id IS NOT NULL")
                    chats = cursor.fetchall()
                    for c in chats:
                        if c['chat_id']:
                            await bot.send_message(chat_id=c['chat_id'], text=report_text, parse_mode="HTML", disable_notification=False)

            # 2. ПРОВЕРКА ЦЕНОВЫХ АЛЕРТОВ И ТАЙМЕРОВ
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, chat_id, symbol, target_price, is_recurring, comment, condition, alert_type, created_at FROM alerts")
                alerts = cursor.fetchall()

                for alert in alerts:
                    a_id = alert['id']
                    chat_id = alert['chat_id']
                    symbol = alert['symbol']
                    target_price = alert['target_price']
                    comment = alert['comment']
                    condition = alert['condition']
                    alert_type = alert['alert_type']

                    # Проверка таймера
                    if alert_type == "TIMER":
                        # Если время таймера истекло
                        delete_alert(a_id)
                        await bot.send_message(
                            chat_id=chat_id, 
                            text=f"⏰ <b>ВНИМАНИЕ! ТАЙМЕР СРАБОТАЛ!</b>\n{comment}", 
                            parse_mode="HTML", 
                            disable_notification=False # ЗВУКОВОЙ СИГНАЛ!
                        )
                        continue

                    # Проверка ценовых алертов BingX
                    df = await fetch_klines(symbol, "1m", limit=2)
                    if df is not None and len(df) > 0:
                        current_price = float(df.iloc[-1]['close'])
                        
                        triggered = False
                        if condition == "cross_above" and current_price >= target_price:
                            triggered = True
                        elif condition == "cross_below" and current_price <= target_price:
                            triggered = True

                        if triggered:
                            coin = symbol.replace("-USDT", "")
                            msg = (
                                f"🚨 <b>АЛЕРТ СРАБОТАЛ!</b>\n\n"
                                f"📌 <b>Актив:</b> {coin}\n"
                                f"🎯 <b>Целевой уровень:</b> `{target_price}`\n"
                                f"📊 <b>Текущая цена:</b> `{current_price}`\n"
                                f"📝 <b>Заметка:</b> {comment}"
                            )
                            # Отправляем сообщение со СТРОГИМ ВКЛЮЧЕНИЕМ ЗВУКА
                            await bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML", disable_notification=False)
                            delete_alert(a_id)

        except Exception as e:
            pass

        # Пауза между проверками цены BingX (12 секунд)
        await asyncio.sleep(12)
