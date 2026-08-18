import asyncio
import logging
from datetime import datetime, timezone, timedelta
import pandas as pd
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import TELEGRAM_BOT_TOKEN
from core.database import init_db, get_connection, delete_alert
from core.ai_handler import clean_symbol
from core.handlers import register_custom_handlers
from core.fetcher import fetch_klines, get_ticker_price
from core.bingx.candles import get_all_usdt_pairs # Новый импорт для получения всех пар
from core.patterns import analyze_patterns
from core.formatter import format_report # Обновленный импорт

MSK_TZ = timezone(timedelta(hours=3))
MY_CHAT_ID = 8029964519  # Твой личный Telegram ID (замени на свой)

TF_PRIORITY = {"1w": 4, "1d": 3, "4h": 2, "1h": 1, "15m": 0}

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

async def check_price_alerts(bot: Bot):
    """Фоновый цикл проверки ценовых алертов."""
    while True:
        try:
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
                        # Если время таймера истекло, удаляем и отправляем уведомление
                        # TODO: Реализовать логику таймера, сейчас это просто удаление.
                        # Допустим, 'comment' содержит информацию о времени срабатывания для таймера
                        # Сейчас просто удаляем и уведомляем
                        
                        delete_alert(a_id)
                        await bot.send_message(
                            chat_id=chat_id, 
                            text=f"⏰ <b>ВНИМАНИЕ! ТАЙМЕР СРАБОТАЛ!</b>\n{comment}", 
                            parse_mode="HTML", 
                            disable_notification=False # ЗВУКОВОЙ СИГНАЛ!
                        )
                        continue

                    # Проверка ценовых алертов BingX
                    # Используем get_ticker_price для быстрой проверки текущей цены
                    current_price = await get_ticker_price(symbol)
                    
                    if current_price == 0.0:
                        logging.warning(f"Не удалось получить текущую цену для {symbol} при проверке алерта {a_id}")
                        continue

                    triggered = False
                    # Предполагается, что 'condition' может быть 'cross_above' или 'cross_below'
                    if condition == "cross_above" and current_price >= target_price:
                        triggered = True
                    elif condition == "cross_below" and current_price <= target_price:
                        triggered = True
                    # Если условие не задано (null), по умолчанию считаем "cross"
                    elif condition is None:
                        # Для алертов без явного условия, срабатываем при любом пересечении
                        # То есть, если текущая цена была ниже, а стала выше, или наоборот
                        # Это требует хранения предыдущей цены, что пока не реализовано в БД.
                        # Для простоты, пока сработает на "точном" совпадении или первом пересечении.
                        # В текущей реализации, без истории, это будет срабатывать как '>= target'
                        # для первоначальной установки или если цена изменится.
                        # Более точная логика пересечения потребует расширения БД.
                        triggered = (current_price >= target_price) or (current_price <= target_price) # Простая заглушка

                    if triggered:
                        coin = clean_symbol(symbol)
                        msg = (
                            f"🚨 <b>АЛЕРТ СРАБОТАЛ!</b>\n\n"
                            f"📌 <b>Актив:</b> {coin}\n"
                            f"🎯 <b>Целевой уровень:</b> `{target_price}`\n"
                            f"📊 <b>Текущая цена:</b> `{current_price}`\n"
                            f"📝 <b>Заметка:</b> {comment}"
                        )
                        # Отправляем сообщение со СТРОГИМ ВКЛЮЧЕНИЕМ ЗВУКА
                        await bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML", disable_notification=False)
                        delete_alert(a_id) # Удаляем сработавший алерт
                        logging.info(f"Алерт {a_id} сработал для {symbol} на {current_price}")

        except Exception as e:
            logging.error(f"Ошибка в цикле проверки алертов: {e}")

        # Пауза между проверками цен BingX (12 секунд), чтобы не перегружать API
        await asyncio.sleep(12)

async def run_auto_schedule(bot: Bot):
    """
    Фоновый цикл автосканирования за 5 минут до каждого часа,
    с учетом закрытия баров по MSK.
    """
    while True:
        now_msk = datetime.now(MSK_TZ)
        
        # Определяем время следующего запуска (XX:55 каждой свечи)
        # Если сейчас 17:54, следующий запуск будет в 17:55.
        # Если сейчас 17:56, следующий запуск будет в 18:55.
        next_run = now_msk.replace(minute=55, second=0, microsecond=0)
        if now_msk.minute >= 55:
            next_run += timedelta(hours=1)
            
        sleep_sec = (next_run - now_msk).total_seconds()
        
        logging.info(f"⏳ Следующий АвтоОтчёт запланирован на {next_run.strftime('%d.%m.%Y %H:%M:%S')} MSK (через {int(sleep_sec)} сек)")
        await asyncio.sleep(sleep_sec)
        
        run_dt = datetime.now(MSK_TZ) # Фактическое время запуска
        hour = run_dt.hour
        weekday = run_dt.weekday() # 0 = ПН, 6 = ВС
        
        timeframes_to_scan = ["1h"] # Всегда сканируем 1h
        
        # 4H сканирование в 02:55, 06:55, 10:55, 14:55, 18:55, 22:55 MSK
        if hour in [2, 6, 10, 14, 18, 22]:
            timeframes_to_scan.append("4h")
            
        # 1D сканирование в 02:55 MSK (закрытие суток)
        if hour == 2:
            timeframes_to_scan.append("1d")
            
            # 1W сканирование в ночь с ВС на ПН в 02:55 MSK (для MSK это понедельник 02:55)
            if weekday == 0: # Понедельник
                timeframes_to_scan.append("1w")
                
        timeframes_to_scan = list(set(timeframes_to_scan))
        logging.info(f"🚀 Запуск АвтоОтчёта для ТФ: {timeframes_to_scan} в {run_dt.strftime('%H:%M')} MSK (5 минут до закрытия)")
        
        coins = await get_all_usdt_pairs() # Получаем все доступные пары с BingX
        all_signals = []
        
        for tf in timeframes_to_scan:
            for coin_full in coins: # coin_full будет типа "BTC-USDT"
                try:
                    # Для автоотчета берем последние 5 свечей, чтобы многобарные паттерны могли быть найдены
                    # analyze_patterns будет работать с этими 5 свечами
                    klines_for_patterns = await fetch_klines(coin_full, tf, limit=5)
                    
                    if klines_for_patterns:
                        df_patterns = pd.DataFrame(klines_for_patterns)
                        
                        # analyze_patterns будет смотреть на df_patterns.iloc[-1] (формирующийся) или [-2], [-3] (закрытые)
                        # для многобарных паттернов.
                        # Если паттерн найден на текущем (формирующемся) баре, это то, что нужно.
                        pats_found = analyze_patterns(df_patterns) 
                        
                        if pats_found != "-": # Если паттерн найден
                            # Определяем направление по текущему формирующемуся бару (последний в df_patterns)
                            curr_forming_candle = df_patterns.iloc[-1]
                            direction = "bull" if curr_forming_candle['close'] >= curr_forming_candle['open'] else "bear"
                            
                            all_signals.append({
                                "symbol": clean_symbol(coin_full),
                                "tf": tf,
                                "pattern": pats_found, # Теперь это строка с названием паттерна
                                "direction": direction,
                                "is_auto": True, # Флаг для formatter
                                "timestamp": curr_forming_candle['time'] # Добавляем timestamp для форматирования времени
                            })
                except Exception as e:
                    logging.error(f"Ошибка получения или анализа {coin_full} {tf}: {e}")
                    
        # СОРТИРОВКА: 1. По алфавиту монеты, 2. По ТФ от большего к меньшим
        # TF_PRIORITY определен в main.py, используется глобальный.
        all_signals.sort(key=lambda x: (x["symbol"], -TF_PRIORITY.get(x["tf"].lower(), 0)))
        
        # Используем обновленный format_report
        report_text = format_report(all_signals, is_auto=True, now_dt=run_dt)
            
        try:
            # Отправляем админу/активному чату со ЗВУКОМ
            # MY_CHAT_ID является обязательным для автоотчетов
            if MY_CHAT_ID:
                await bot.send_message(chat_id=MY_CHAT_ID, text=report_text, parse_mode="HTML")
                logging.info(f"✅ АвтоОтчёт успешно отправлен пользователю {MY_CHAT_ID}")
            else:
                logging.warning("MY_CHAT_ID не установлен, автоотчёт не будет отправлен.")
        except Exception as err:
            logging.error(f"❌ Ошибка отправки АвтоОтчёта: {err}")

async def main():
    init_db()
    register_custom_handlers(dp, bot)
    
    # Запускаем фоновые задачи
    asyncio.create_task(check_price_alerts(bot)) # Новая задача для проверки алертов
    asyncio.create_task(run_auto_schedule(bot)) # Обновленная задача автосканирования

    logging.info("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
