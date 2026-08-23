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
from core.ai_handler import clean_symbol
from core.handlers import register_custom_handlers
from core.fetcher import fetch_klines, get_ticker_price
from core.bingx.candles import get_all_usdt_pairs
from core.patterns import analyze_patterns
from core.formatter import format_report

MY_CHAT_ID = 8029964519

TF_PRIORITY = {"1w": 4, "1d": 3, "4h": 2, "1h": 1, "15m": 0}

# Настройка логирования с ротацией
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

async def set_main_menu(bot: Bot):
    """Устанавливает кнопки меню."""
    commands = [
        BotCommand(command="/start", description="👋 Запустить бота"),
        BotCommand(command="/help", description="❓ Помощь"),
        BotCommand(command="/scan", description="🔍 Полное сканирование"),
        BotCommand(command="/scan_1h", description="📊 Скан 1H"),
        BotCommand(command="/scan_4h", description="📊 Скан 4H"),
        BotCommand(command="/scan_1d", description="📊 Скан 1D"),
        BotCommand(command="/scan_1w", description="📊 Скан 1W"),
        BotCommand(command="/alerts", description="🔔 Мои алерты"),
        BotCommand(command="/del_all", description="🗑 Удалить все алерты"),
        BotCommand(command="/price", description="💰 Узнать цену"),
        BotCommand(command="/restart_bot", description="🔄 Перезапустить бота")
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    logging.info("Меню команд обновлено.")

async def check_price_alerts(bot: Bot):
    """Фоновый цикл проверки ценовых алертов."""
    while True:
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, chat_id, symbol, target_price, condition, alert_type, is_recurring, triggered_count, note, created_at FROM alerts")
                alerts = cursor.fetchall()

                for alert in alerts:
                    a_id = alert['id']
                    chat_id = alert['chat_id']
                    symbol = alert['symbol']
                    target_price = alert['target_price']
                    note = alert['note']
                    condition = alert['condition']
                    alert_type = alert['alert_type']
                    is_recurring = bool(alert['is_recurring'])
                    triggered_count = alert['triggered_count']

                    if alert_type == "TIMER":
                        delete_alert(a_id)
                        await bot.send_message(chat_id=chat_id, text=f"⏰ <b>ВНИМАНИЕ! ТАЙМЕР СРАБОТАЛ!</b>\n{note}", parse_mode="HTML", disable_notification=False)
                        continue

                    current_price = await get_ticker_price(symbol)
                    
                    if current_price == 0.0:
                        logging.warning(f"Не удалось получить текущую цену для {symbol} при проверке алерта {a_id}. Пропускаем.")
                        continue

                    triggered = False
                    prev_price = None
                    try:
                        klines = await fetch_klines(symbol, "1m", limit=2) 
                        if klines and len(klines) >= 2:
                            prev_price = float(klines[-2]['close'])
                    except Exception as k_e:
                        logging.warning(f"Не удалось получить klines для {symbol} для prev_price: {k_e}")
                    
                    if condition == "cross_above":
                        if current_price >= target_price:
                            if prev_price is None or prev_price < target_price:
                                triggered = True
                    elif condition == "cross_below":
                        if current_price <= target_price:
                            if prev_price is None or prev_price > target_price:
                                triggered = True
                    elif condition == "cross":
                        if prev_price is not None:
                            if (prev_price < target_price and current_price >= target_price) or \
                               (prev_price > target_price and current_price <= target_price):
                                triggered = True
                        else:
                            if abs(current_price - target_price) < target_price * 0.0001:
                                triggered = True

                    if triggered:
                        coin = clean_symbol(symbol)
                        msg = (
                            f"🚨 <b>АЛЕРТ СРАБОТАЛ!</b>\n\n"
                            f"📌 <b>Актив:</b> {coin}\n"
                            f"🎯 <b>Целевой уровень:</b> <code>{target_price:.2f}</code>\n"
                            f"📊 <b>Текущая цена:</b> <code>{current_price:.2f}</code>\n"
                            f"📝 <b>Примечание:</b> {note}"
                        )
                        
                        reply_markup = None
                        if not is_recurring:
                            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="🔁 Сделать многоразовым", callback_data=f"set_recurring_{a_id}")]
                            ])
                            reply_markup = keyboard
                            
                        await bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML", disable_notification=False, reply_markup=reply_markup)
                        
                        update_alert_triggered_status(a_id, increment_count=True)
                        
                        if not is_recurring:
                            delete_alert(a_id, chat_id=chat_id)
                        
                        logging.info(f"Алерт {a_id} сработал для {symbol} на {current_price}. Многоразовый: {is_recurring}")

        except Exception as e:
            logging.error(f"FATAL ERROR in check_price_alerts loop: {e}", exc_info=True)
            await asyncio.sleep(60)
            continue

        await asyncio.sleep(12)

async def run_auto_schedule(bot: Bot):
    """Фоновый цикл автосканирования."""
    while True:
        try:
            now_msk = datetime.now(MSK_TZ)
            next_run = now_msk.replace(minute=55, second=0, microsecond=0)
            if now_msk.minute >= 55:
                next_run += timedelta(hours=1)
                
            sleep_sec = (next_run - now_msk).total_seconds()
            while sleep_sec < 0:
                next_run += timedelta(hours=1)
                sleep_sec = (next_run - now_msk).total_seconds()

            logging.info(f"⏳ Следующий АвтоОтчёт запланирован на {next_run.strftime('%d.%m.%Y %H:%M:%S')} MSK (через {int(sleep_sec)} сек)")
            await asyncio.sleep(sleep_sec)
            
            run_dt = datetime.now(MSK_TZ) 
            hour = run_dt.hour
            weekday = run_dt.weekday()
            
            timeframes_to_scan = ["1h"]
            if hour in [2, 6, 10, 14, 18, 22]:
                timeframes_to_scan.append("4h")
            if hour == 2:
                timeframes_to_scan.append("1d")
                if weekday == 0:
                    timeframes_to_scan.append("1w")
                    
            timeframes_to_scan = list(set(timeframes_to_scan))
            logging.info(f"🚀 Запуск АвтоОтчёта для ТФ: {timeframes_to_scan} в {run_dt.strftime('%H:%M')} MSK")
            
            coins = await get_all_usdt_pairs()
            if not coins:
                logging.warning("Не удалось получить список USDT пар для автосканирования.")
                continue

            all_signals = []
            
            for tf in timeframes_to_scan:
                candle_close_time_msk = run_dt.replace(minute=0, second=0, microsecond=0)
                candle_close_time_utc = candle_close_time_msk.astimezone(timezone.utc)
                end_time_ms_for_fetch = int(candle_close_time_utc.timestamp() * 1000)

                for coin_full in coins:
                    try:
                        limit_needed = 500 
                        klines_for_analysis = await fetch_klines(symbol=coin_full, timeframe=tf, limit=limit_needed, end_time_ms=end_time_ms_for_fetch)
                        
                        if klines_for_analysis and len(klines_for_analysis) >= 3:
                            df_patterns = pd.DataFrame(klines_for_analysis)
                            pat_data = analyze_patterns(df_patterns) 
                            last_closed_candle_api_time_ms = df_patterns.iloc[-1]['time']
                            
                            all_signals.append({
                                "symbol": clean_symbol(coin_full),
                                "tf": tf,
                                "pattern": pat_data["pattern"], 
                                "direction_bb": pat_data.get("direction_bb", '⚪⚪⚪'),
                                "state_emoji": pat_data.get("state_emoji", ''),
                                "is_auto": True, 
                                "timestamp": last_closed_candle_api_time_ms
                            })
                    except Exception as e:
                        logging.error(f"Ошибка получения или анализа {coin_full} {tf}: {e}", exc_info=True)
                        
            all_signals.sort(key=lambda x: (x["symbol"], -TF_PRIORITY.get(x["tf"].lower(), 0)))
            report_text = format_report(all_signals, is_auto=True, now_dt=run_dt)
                
            try:
                if MY_CHAT_ID:
                    await bot.send_message(chat_id=MY_CHAT_ID, text=report_text, parse_mode="HTML")
                    logging.info(f"✅ АвтоОтчёт успешно отправлен пользователю {MY_CHAT_ID}")
            except Exception as err:
                logging.error(f"❌ Ошибка отправки АвтоОтчёта: {err}", exc_info=True)

        except Exception as e:
            logging.error(f"FATAL ERROR in run_auto_schedule loop: {e}", exc_info=True)
            await asyncio.sleep(60)
            continue

async def main():
    init_db()
    
    # Создаем бота и диспетчер
    bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    
    # Регистрируем хендлеры
    register_custom_handlers(dp, bot)
    
    # Устанавливаем меню команд
    await set_main_menu(bot)
    
    # Запускаем фоновые задачи
    asyncio.create_task(check_price_alerts(bot))
    asyncio.create_task(run_auto_schedule(bot))

    logging.info("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
