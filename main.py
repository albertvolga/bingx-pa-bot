import asyncio
import logging
from datetime import datetime, timedelta, timezone
import pandas as pd
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, BotCommandScopeDefault
from config import TELEGRAM_BOT_TOKEN, MSK_TZ
from core.database import init_db, get_connection, delete_alert, update_alert_triggered_status, set_alert_recurring
from core.fetcher import fetch_klines, get_ticker_price
from core.bingx.candles import get_all_usdt_pairs
from core.patterns import analyze_patterns
from core.formatter import format_report
from core.handlers import register_custom_handlers

MY_CHAT_ID = 8029964519
TF_PRIORITY = {"1w": 4, "1d": 3, "4h": 2, "1h": 1}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

async def set_main_menu(bot: Bot):
    commands = [
        BotCommand(command="/start", description="👋 Запустить"),
        BotCommand(command="/scan", description="🔍 Скан всех ТФ"),
        BotCommand(command="/scan_1h", description="📊 Скан 1H"),
        BotCommand(command="/scan_4h", description="📊 Скан 4H"),
        BotCommand(command="/scan_1d", description="📊 Скан 1D"),
        BotCommand(command="/alerts", description="🔔 Мои алерты"),
        BotCommand(command="/del_all", description="🗑 Удалить все"),
        BotCommand(command="/restart_bot", description="🔄 Перезапуск")
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    logging.info("Меню обновлено.")

async def check_price_alerts(bot: Bot):
    while True:
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, chat_id, symbol, target_price, condition, is_recurring, note FROM alerts WHERE alert_type='PRICE'")
                alerts = cursor.fetchall()
                for alert in alerts:
                    a_id, chat_id, symbol, target, cond, is_rec, note = alert['id'], alert['chat_id'], alert['symbol'], alert['target_price'], alert['condition'], bool(alert['is_recurring']), alert['note']
                    
                    current_price = await get_ticker_price(symbol)
                    if current_price == 0.0: continue

                    triggered = False
                    # Получаем prev_price корректно
                    prev_price = None
                    try:
                        klines = await fetch_klines(symbol, "1m", limit=2)
                        if klines is not None and not klines.empty and len(klines) >= 2:
                            prev_price = float(klines.iloc[-2]['close'])
                    except: pass
                    
                    if cond == "cross_above" and current_price >= target and (prev_price is None or prev_price < target): triggered = True
                    elif cond == "cross_below" and current_price <= target and (prev_price is None or prev_price > target): triggered = True
                    elif cond == "cross" and prev_price is not None and ((prev_price < target and current_price >= target) or (prev_price > target and current_price <= target)): triggered = True
                    elif cond == "cross" and prev_price is None and abs(current_price - target) < target * 0.001: triggered = True

                    if triggered:
                        msg = f"🚨 <b>АЛЕРТ!</b>\n{symbol}: {target} -> {current_price}\n{note}"
                        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔁 Многоразовый", callback_data=f"set_recurring_{a_id}")]]) if not is_rec else None
                        await bot.send_message(chat_id, msg, parse_mode="HTML", disable_notification=False, reply_markup=kb)
                        update_alert_triggered_status(a_id, increment_count=True)
                        if not is_rec: delete_alert(a_id, chat_id=chat_id)
        except Exception as e:
            logging.error(f"Alert Loop Error: {e}")
        await asyncio.sleep(12)

async def run_auto_schedule(bot: Bot):
    while True:
        try:
            now_msk = datetime.now(MSK_TZ)
            next_run = now_msk.replace(minute=55, second=0, microsecond=0)
            if now_msk.minute >= 55: next_run += timedelta(hours=1)
            sleep_sec = (next_run - now_msk).total_seconds()
            if sleep_sec < 0: sleep_sec = 0
            
            logging.info(f"След. отчет в {next_run.strftime('%H:%M')} (через {int(sleep_sec)}с)")
            await asyncio.sleep(sleep_sec)
            
            run_dt = datetime.now(MSK_TZ)
            tfs = ["1h"]
            if run_dt.hour in [2, 6, 10, 14, 18, 22]: tfs.append("4h")
            if run_dt.hour == 2:
                tfs.append("1d")
                if run_dt.weekday() == 0: tfs.append("1w")
            
            coins = await get_all_usdt_pairs()
            if not coins: continue
            
            all_signals = []
            close_time_msk = run_dt.replace(minute=0, second=0, microsecond=0)
            end_time_ms = int(close_time_msk.astimezone(timezone.utc).timestamp() * 1000)
            
            for tf in tfs:
                for coin in coins:
                    try:
                        klines = await fetch_klines(coin, tf, limit=500, end_time_ms=end_time_ms)
                        if klines is None or klines.empty or len(klines) < 3: continue
                        
                        # Передаем список словарей в analyze_patterns
                        candles_list = klines.to_dict('records')
                        pat = analyze_patterns(candles_list)
                        
                        if pat and pat.get("pattern") and pat["pattern"] != "-":
                            last_candle = klines.iloc[-1]
                            all_signals.append({
                                "symbol": coin.replace("-USDT", ""),
                                "tf": tf,
                                "pattern": pat["pattern"],
                                "direction_bb": pat.get("direction_bb", '⚪⚪⚪'),
                                "state_emoji": pat.get("state_emoji", ''),
                                "is_auto": True,
                                "timestamp": last_candle['time']
                            })
                    except Exception as e:
                        logging.debug(f"Scan error {coin} {tf}: {e}")
            
            if all_signals:
                report = format_report(all_signals, is_auto=True, now_dt=run_dt)
                try: await bot.send_message(MY_CHAT_ID, report, parse_mode="HTML")
                except: pass
            else:
                logging.info("Паттернов не найдено.")
                
        except Exception as e:
            logging.error(f"AutoScan Error: {e}")
            await asyncio.sleep(60)

async def main():
    init_db()
    bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    
    register_custom_handlers(dp, bot)
    await set_main_menu(bot)
    
    asyncio.create_task(check_price_alerts(bot))
    asyncio.create_task(run_auto_schedule(bot))
    
    logging.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
