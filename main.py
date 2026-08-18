import asyncio
import logging
from datetime import datetime, timezone, timedelta
import pandas as pd
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import TELEGRAM_BOT_TOKEN
from core.database import init_db, get_connection, delete_alert, update_alert_triggered_status, set_alert_recurring
from core.ai_handler import clean_symbol
from core.handlers import register_custom_handlers
from core.fetcher import fetch_klines, get_ticker_price
from core.bingx.candles import get_all_usdt_pairs # Новый импорт для получения всех пар
from core.patterns import analyze_patterns # calculate_indicators_and_states # Пока без calculate_indicators_and_states
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

                    # Проверка таймера
                    if alert_type == "TIMER":
                        # TODO: Реализовать логику таймера, сейчас это просто удаление
                        delete_alert(a_id)
                        await bot.send_message(
                            chat_id=chat_id, 
                            text=f"⏰ <b>ВНИМАНИЕ! ТАЙМЕР СРАБОТАЛ!</b>\n{note}", 
                            parse_mode="HTML", 
                            disable_notification=False # ЗВУКОВОЙ СИГНАЛ!
                        )
                        continue

                    # Проверка ценовых алертов BingX
                    current_price = await get_ticker_price(symbol)
                    
                    if current_price == 0.0:
                        logging.warning(f"Не удалось получить текущую цену для {symbol} при проверке алерта {a_id}")
                        continue

                    triggered = False
                    # Логика срабатывания (condition)
                    if condition == "cross_above" and current_price >= target_price:
                        triggered = True
                    elif condition == "cross_below" and current_price <= target_price:
                        triggered = True
                    elif condition == "cross": # Для условия "cross" срабатывает при любом пересечении
                        # Эта логика требует хранения предыдущей цены, что пока не реализовано в БД.
                        # Для простоты, пока сработает как ">= target" для первоначальной установки или если цена изменится.
                        # Более точная логика пересечения потребует расширения БД или более частых проверок.
                        # Пока срабатывает при достижении цели, как в случае cross_above/below,
                        # но без учета "пересечения" как такового.
                        triggered = (current_price >= target_price - 0.0001) and (current_price <= target_price + 0.0001) # Точное попадание
                        # или более универсально: abs(current_price - target_price) < tolerance
                        # Или просто current_price == target_price, но это рискованно с float.
                        # Для реального "cross" нужно знать было ли раньше ниже/выше.
                        # Пока упрощаем: если цена равна или "пересекла" цель
                        # Для первого срабатывания можно использовать (current_price >= target_price and previous_price < target_price)
                        # или (current_price <= target_price and previous_price > target_price)
                        # Так как предыдущей цены нет, используем простую проверку на достижение.
                        triggered = (current_price >= target_price if target_price > 0 else current_price <= target_price) # Простая заглушка

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
                            # Для одноразовых алертов предлагаем сделать многоразовым
                            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="🔁 Сделать многоразовым", callback_data=f"set_recurring_{a_id}")]
                            ])
                            reply_markup = keyboard
                            
                        # Отправляем сообщение со СТРОГИМ ВКЛЮЧЕНИЕМ ЗВУКА
                        await bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML", disable_notification=False, reply_markup=reply_markup)
                        
                        update_alert_triggered_status(a_id, increment_count=True) # Увеличиваем счетчик
                        
                        if not is_recurring:
                            delete_alert(a_id, chat_id=chat_id) # Удаляем сработавший одноразовый алерт
                        
                        logging.info(f"Алерт {a_id} сработал для {symbol} на {current_price}. Многоразовый: {is_recurring}")

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
                    # Для автоотчета берем достаточно свечей для анализа паттернов и индикаторов (BB480)
                    limit_needed = 500 # Достаточно для BB(480) + паттерны
                    klines_for_analysis = await fetch_klines(coin_full, tf, limit=limit_needed)
                    
                    if klines_for_analysis and len(klines_for_analysis) >= 3: # Для анализа нужно мин 3
                        df_patterns = pd.DataFrame(klines_for_analysis)
                        
                        # analyze_patterns теперь возвращает dict с паттерном, direction_bb и state_emoji
                        pat_data = analyze_patterns(df_patterns) 
                        
                        if pat_data and pat_data["pattern"] != "-": 
                            # Определяем направление по текущему формирующемуся бару (последний в df_patterns)
                            curr_forming_candle = df_patterns.iloc[-1]
                            
                            all_signals.append({
                                "symbol": clean_symbol(coin_full),
                                "tf": tf,
                                "pattern": pat_data["pattern"], 
                                "direction_bb": pat_data.get("direction_bb", '⚪⚪⚪'), # Из analyze_patterns
                                "state_emoji": pat_data.get("state_emoji", ''), # Из analyze_patterns
                                "is_auto": True, # Флаг для formatter
                                "timestamp": curr_forming_candle['time'] # Добавляем timestamp для форматирования времени
                            })
                except Exception as e:
                    logging.error(f"Ошибка получения или анализа {coin_full} {tf}: {e}")
                    
        # СОРТИРОВКА: 1. По алфавиту монеты, 2. По ТФ от большего к меньшим
        # TF_PRIORITY определен глобально
        all_signals.sort(key=lambda x: (x["symbol"], -TF_PRIORITY.get(x["tf"].lower(), 0)))
        
        # Используем обновленный format_report
        report_text = format_report(all_signals, is_auto=True, now_dt=run_dt)
            
        try:
            # Отправляем админу/активному чату со ЗВУКОМ
            if MY_CHAT_ID:
                await bot.send_message(chat_id=MY_CHAT_ID, text=report_text, parse_mode="HTML")
                logging.info(f"✅ АвтоОтчёт успешно отправлен пользователю {MY_CHAT_ID}")
            else:
                logging.warning("MY_CHAT_ID не установлен, автоотчёт не будет отправлен.")
        except Exception as err:
            logging.error(f"❌ Ошибка отправки АвтоОтчёта: {err}")

async def main():
    init_db() # Вызываем инициализацию БД здесь один раз
    register_custom_handlers(dp, bot)
    
    # Запускаем фоновые задачи
    asyncio.create_task(check_price_alerts(bot)) # Новая задача для проверки алертов
    asyncio.create_task(run_auto_schedule(bot)) # Обновленная задача автосканирования

    logging.info("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
