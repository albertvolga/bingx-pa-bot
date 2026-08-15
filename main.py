import asyncio
import logging
import pandas as pd
from datetime import datetime, timezone, timedelta
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN, USER_ID
from core.handlers import router, run_scan
from core.fetcher import fetch_klines
from core.patterns import analyze_patterns
from core.database import get_all_alerts, delete_alert

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(router)

MSK_TZ = timezone(timedelta(hours=3))

async def check_user_alerts():
    alerts = get_all_alerts()
    if not alerts:
        return

    for aid, chat_id, sym, tf, pat, is_repeating in alerts:
        try:
            klines = await fetch_klines(sym, interval=tf, limit=10)
            if not klines or len(klines) < 3:
                continue
            df = pd.DataFrame(klines)
            found_pats = analyze_patterns(df)
            
            if pat.upper() in [p.upper() for p in found_pats]:
                alert_type = "🔄 Многоразовый" if is_repeating else "1️⃣ Одноразовый"
                msg_text = (
                    f"🚨 <b>СРАБОТАЛ АЛЕРТ!</b> ({alert_type})\n\n"
                    f"🔹 <b>Инструмент:</b> {sym}\n"
                    f"🔹 <b>Таймфрейм:</b> {tf.upper()}\n"
                    f"🔹 <b>Паттерн:</b> {pat.upper()}"
                )
                # disable_notification=False гарантирует пуш-уведомление со звуком
                await bot.send_message(chat_id=chat_id, text=msg_text, parse_mode="HTML", disable_notification=False)
                
                # Если алерт одноразовый — удаляем из БД
                if not is_repeating:
                    delete_alert(aid)
        except Exception as e:
            logging.error(f"Ошибка проверки алерта #{aid}: {e}")

async def auto_report_scheduler():
    while True:
        now_dt = datetime.now(MSK_TZ)
        next_hour = (now_dt + timedelta(hours=1)).replace(minute=55, second=0, microsecond=0)
        if now_dt.minute >= 55:
            next_hour = (now_dt + timedelta(hours=1)).replace(minute=55, second=0, microsecond=0)
            
        sleep_seconds = (next_hour - now_dt).total_seconds()
        logging.info(f"⏳ Следующий АвтоОтчёт запланирован на {next_hour.strftime('%d.%m.%Y %H:%M:%S')} MSK (через {int(sleep_seconds)} сек)")
        
        # Раз в 60 секунд между автоотчетами проверяем алерты
        check_interval = 60
        elapsed = 0
        while elapsed < sleep_seconds:
            await asyncio.sleep(check_interval)
            elapsed += check_interval
            await check_user_alerts()

        # Запуск часового автоотчета
        try:
            class DummyMessage:
                def __init__(self, bot, chat_id):
                    self.bot = bot
                    self.chat_id = chat_id
                async def answer(self, text, parse_mode=None, reply_markup=None):
                    return await self.bot.send_message(chat_id=self.chat_id, text=text, parse_mode=parse_mode, reply_markup=reply_markup, disable_notification=False)

            dummy_msg = DummyMessage(bot, USER_ID)
            await run_scan(dummy_msg, interval="all", is_auto=True)
        except Exception as e:
            logging.error(f"Ошибка автоотчета: {e}")

async def main():
    logging.info("Бот успешно запущен с обновленной системой алертов!")
    asyncio.create_task(auto_report_scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
