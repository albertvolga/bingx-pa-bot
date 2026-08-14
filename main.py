import asyncio
import logging
from datetime import datetime, timezone, timedelta
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import TELEGRAM_BOT_TOKEN
from core.database import init_db
from core.ai_handler import timer_checker_loop
from core.handlers import register_custom_handlers, clean_symbol
from core.fetcher import fetch_klines
from core.patterns import analyze_patterns
from core.formatter import format_table_report

MSK_TZ = timezone(timedelta(hours=3))
MY_CHAT_ID = 8976473612  # Ваш ID

TF_PRIORITY = {"1w": 4, "1d": 3, "4h": 2, "1h": 1, "15m": 0}

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

async def run_auto_schedule():
    """Фоновый цикл автосканирования за 5 минут до каждого часа"""
    while True:
        now = datetime.now(MSK_TZ)
        
        # Ближайшая 55-я минута текущего или следующего часа
        next_run = now.replace(minute=55, second=0, microsecond=0)
        if now >= next_run:
            next_run += timedelta(hours=1)
            
        sleep_sec = (next_run - now).total_seconds()
        logging.info(f"⏳ Следующий АвтоОтчёт запланирован на {next_run.strftime('%d.%m.%Y %H:%M:%S')} MSK (через {int(sleep_sec)} сек)")
        await asyncio.sleep(sleep_sec)
        
        run_dt = datetime.now(MSK_TZ)
        hour = run_dt.hour
        weekday = run_dt.weekday() # 0 = ПН, 6 = ВС
        
        # Определяем список ТФ для сканирования
        timeframes = ["1h"]
        
        # 4H сканирование в 02:55, 06:55, 10:55, 14:55, 18:55, 22:55
        if hour in [2, 6, 10, 14, 18, 22]:
            timeframes.append("4h")
            
        # 1D сканирование в 02:55 MSK (закрытие суток)
        if hour == 2:
            timeframes.append("1d")
            
            # 1W сканирование в ночь с ВС на ПН в 02:55 MSK
            if weekday == 0 or (weekday == 6 and hour == 2):
                timeframes.append("1w")
                
        timeframes = list(set(timeframes))
        logging.info(f"🚀 Запуск АвтоОтчёта для ТФ: {timeframes}")
        
        # Список активов включая Золото (XAU-USDT) и Серебро (XAG-USDT)
        coins = [
            "BTC-USDT", "ETH-USDT", "SOL-USDT", "KAS-USDT", "LTC-USDT", 
            "DOT-USDT", "DOGE-USDT", "ATOM-USDT", "ADA-USDT",
            "XAU-USDT", "XAG-USDT"
        ]
        all_signals = []
        
        for tf in timeframes:
            for coin in coins:
                try:
                    df = await fetch_klines(coin, tf, limit=30)
                    if df is not None:
                        pats = analyze_patterns(df)
                        if pats:
                            curr = df.iloc[-1]
                            direction = "bull" if curr['close'] >= curr['open'] else "bear"
                            for p in pats:
                                all_signals.append({
                                    "symbol": clean_symbol(coin),
                                    "tf": tf,
                                    "pattern": p,
                                    "direction": direction
                                })
                except Exception as e:
                    logging.error(f"Ошибка получения {coin} {tf}: {e}")
                    
        # СОРТИРОВКА: 1. По алфавиту монеты, 2. По ТФ от большего к меньшему
        all_signals.sort(key=lambda x: (x["symbol"], -TF_PRIORITY.get(x["tf"].lower(), 0)))
        
        title = f"📊 АвтоОтчёт ({run_dt.strftime('%d.%m.%Y %H:%M')})"
        
        if all_signals:
            report_text = format_table_report(all_signals, report_title=title, now_dt=run_dt, tf_type="multi")
        else:
            report_text = f"<b>{title}</b>\n\n✅ Интересных паттернов за 5 минут до закрытия свечей не найдено."
            
        try:
            await bot.send_message(chat_id=MY_CHAT_ID, text=report_text, parse_mode="HTML")
        except Exception as err:
            logging.error(f"❌ Ошибка отправки АвтоОтчёта: {err}")

async def main():
    init_db()
    register_custom_handlers(dp, bot)
    
    asyncio.create_task(timer_checker_loop(bot))
    asyncio.create_task(run_auto_schedule())
    
    logging.info("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
