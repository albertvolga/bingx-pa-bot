import logging
import datetime
import pandas as pd
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ContentType
from aiogram.filters import Command

from core.database import delete_alert, get_all_alerts, clear_all_alerts, set_alert_recurring
from core.ai_handler import process_ai_message, clean_symbol
from core.bingx.candles import fetch_bingx_candles, get_all_usdt_pairs # Добавлен get_all_usdt_pairs для динамического списка
from core.patterns import analyze_patterns #, calculate_indicators_and_states # Пока без calculate_indicators_and_states
from core.stt import transcribe_voice
from core.formatter import format_report, format_alerts_table # Импортируем обе функции форматирования
from config import SYMBOL_MAP # Используем SYMBOL_MAP для списка сканирования

router = Router()

def register_custom_handlers(dp, bot=None):
    dp.include_router(router)

# Список символов для сканирования: теперь берем из конфига
# SCAN_SYMBOLS будет использоваться как полный список для /scan
# Для автоотчета берется get_all_usdt_pairs()

def build_compact_keyboard(buttons, row_width=4):
    keyboard = []
    row = []
    for b in buttons:
        row.append(InlineKeyboardButton(text=b["text"], callback_data=b["callback_data"]))
        if len(row) == row_width:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def run_scan(message: Message, interval: str = "all", scan_datetime: datetime = None):
    """
    Запускает сканирование паттернов для ручных команд /scan.
    Может анализировать как последний ЗАКРЫТЫЙ бар, так и исторический бар.
    """
    is_historical_scan = scan_datetime is not None
    now_msk = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)
    
    if is_historical_scan:
        display_time = scan_datetime.strftime('%d.%m.%y %H:%M')
        tf_title = "Все ТФ" if interval == "all" else interval
        status_text = f"🔍 Запускаю историческое сканирование {tf_title} на {display_time} МСК..."
    else:
        display_time = now_msk.strftime('%d.%m.%y %H:%M')
        tf_title = "Все ТФ" if interval == "all" else interval
        status_text = f"🔍 Запускаю сканирование {tf_title} ({display_time} МСК)..."

    status_msg = await message.answer(status_text)

    # Включаем 1w для ручного сканирования
    timeframes = ["1h", "4h", "1d", "1w"] if interval == "all" else [interval]
    all_signals = []

    # Используем ключи из SYMBOL_MAP как список для ручного сканирования
    scan_symbols_list = list(SYMBOL_MAP.keys())

    for sym_short in scan_symbols_list:
        sym_full = SYMBOL_MAP[sym_short] # Получаем полное имя, например BTC-USDT
        
        for tf in timeframes:
            try:
                # Для анализа паттернов и индикаторов нам нужно несколько свечей.
                # Max limit для BB(480) + 3 свечи для паттерна = ~483, округлим до 500.
                limit_needed = 500 

                klines = await fetch_bingx_candles(
                    symbol=sym_full, 
                    timeframe=tf, 
                    limit=limit_needed, 
                    # Если исторический скан, указываем endTime
                    end_time_ms=int(scan_datetime.timestamp() * 1000) if is_historical_scan else None
                )
                
                if not klines or len(klines) < 3: 
                    logging.warning(f"Недостаточно данных для {sym_full} {tf} при сканировании.")
                    continue

                df = pd.DataFrame(klines)
                
                # При историческом сканировании, нам нужна свеча, которая ЗАКРЫЛАСЬ ДО scan_datetime.
                # Если scan_datetime == 11:00, нам нужна свеча, закрывшаяся в 10:00.
                # В BingX API `time` это время ОТКРЫТИЯ свечи.
                # Поэтому, если `scan_datetime` передано, мы хотим анализировать бар, который предшествует `scan_datetime`
                # или заканчивается в `scan_datetime`. 
                # Так как BingX API возвращает свечи по времени ОТКРЫТИЯ, а мы запрашиваем до `end_time_ms`,
                # последняя свеча в `klines` будет самой близкой к `end_time_ms`.
                
                # Для ручного сканирования всегда анализируем последнюю *доступную* свечу в df.
                # analyze_patterns будет работать с df.iloc[-1] для однобарных паттернов
                # и с более ранними для многобарных.
                
                # В `analyze_patterns` будут добавлены расчеты для НАПР и СОСТ
                pat_data = analyze_patterns(df) # analyze_patterns теперь возвращает dict
                
                if pat_data and pat_data["pattern"] != "-": 
                    last_analyzed_candle = df.iloc[-1] 
                    direction_bb = pat_data.get("direction_bb", '⚪⚪⚪') # Заглушка
                    state_emoji = pat_data.get("state_emoji", '') # Заглушка
                    
                    all_signals.append({
                        "symbol": clean_symbol(sym_full),
                        "tf": tf,
                        "pattern": pat_data["pattern"],
                        "direction_bb": direction_bb,
                        "state_emoji": state_emoji,
                        "is_auto": False, # Это ручной скан
                        "timestamp": last_analyzed_candle['time'] # Время ОТКРЫТИЯ последней свечи
                    })
            except Exception as e:
                logging.error(f"Ошибка сканирования {sym_full} {tf}: {e}")

    report_text = format_report(all_signals, is_auto=False, now_dt=now_msk) # now_dt - текущее время для заголовка отчета
    
    await status_msg.edit_text(report_text, parse_mode="HTML")

@router.message(Command("alerts"))
async def cmd_alerts(message: Message):
    alerts_list = get_all_alerts(chat_id=message.chat.id)
    text, buttons = format_alerts_table(alerts_list)
    keyboard = build_compact_keyboard(buttons, row_width=4) if buttons else None
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML") # Добавил parse_mode

@router.message(Command("del_all"))
async def cmd_del_all(message: Message):
    clear_all_alerts(message.chat.id)
    await message.answer("🗑 Все активные алерты успешно удалены!")

# Обработка команды /scan (без параметров или с датой/временем)
@router.message(Command("scan"))
async def cmd_scan_universal(message: Message):
    args = message.text.split()
    scan_dt = None
    if len(args) > 1:
        # Пробуем распарсить дату и время
        try:
            # Ожидаем формат типа "ДД.ММ ЧЧ:ММ" или "ДД.ММ"
            date_time_str = " ".join(args[1:])
            
            # Пробуем полный формат "ДД.ММ ЧЧ:ММ"
            try:
                scan_dt = datetime.strptime(date_time_str, "%d.%m %H:%M").replace(year=now_msk.year)
            except ValueError:
                # Если только дата "ДД.ММ", устанавливаем время по умолчанию 03:00 (закрытие дневной свечи)
                scan_dt = datetime.strptime(date_time_str, "%d.%m").replace(year=now_msk.year, hour=3, minute=0)
            
            scan_dt = scan_dt.replace(tzinfo=datetime.timedelta(hours=3)) # Указываем MSK
            
        except ValueError:
            await message.answer("❌ Неверный формат даты/времени. Используйте <code>/scan ДД.ММ ЧЧ:ММ</code> или <code>/scan ДД.ММ</code>.")
            return

    await run_scan(message, "all", scan_datetime=scan_dt)

@router.message(Command("scan_1h"))
async def cmd_scan_1h(message: Message): await run_scan(message, "1h")

@router.message(Command("scan_4h"))
async def cmd_scan_4h(message: Message): await run_scan(message, "4h")

@router.message(Command("scan_1d"))
async def cmd_scan_1d(message: Message): await run_scan(message, "1d")

@router.message(Command("scan_1w"))
async def cmd_scan_1w(message: Message): await run_scan(message, "1w")

@router.callback_query(F.data.startswith("del_alert_"))
async def process_del_alert(callback: CallbackQuery):
    alert_id = int(callback.data.split("_")[2])
    delete_alert(alert_id, chat_id=callback.message.chat.id)
    await callback.answer("Алерт удален!")
    
    alerts_list = get_all_alerts(chat_id=callback.message.chat.id)
    text, buttons = format_alerts_table(alerts_list)
    keyboard = build_compact_keyboard(buttons, row_width=4) if buttons else None
    
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logging.warning(f"Ошибка при обновлении сообщения после удаления алерта: {e}")
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML") # Отправляем новое, если старое не обновить

@router.callback_query(F.data.startswith("set_recurring_"))
async def process_set_recurring(callback: CallbackQuery):
    alert_id = int(callback.data.split("_")[2])
    set_alert_recurring(alert_id, True)
    await callback.answer("Алерт установлен как многоразовый!")
    # После установки многоразовости, сообщение можно обновить или оставить как есть.
    # Пока просто уберем кнопку и обновим текст.
    # alerts_list = get_all_alerts(chat_id=callback.message.chat.id)
    # text, buttons = format_alerts_table(alerts_list) # Эта функция не для такого типа обновления
    # await callback.message.edit_text(text, reply_markup=build_compact_keyboard(buttons, row_width=4), parse_mode="HTML")
    await callback.message.edit_reply_markup(reply_markup=None) # Убираем кнопки, если это был алерт-триггер
    await callback.message.answer(f"✅ Алерт #{alert_id} теперь многоразовый.", parse_mode="HTML")


# Обработка голосовых сообщений
@router.message(F.content_type == ContentType.VOICE)
async def handle_voice_message(message: Message):
    status_msg = await message.answer("🎙 Расшифровываю голос...")
    try:
        file_info = await message.bot.get_file(message.voice.file_id)
        voice_bytes = await message.bot.download_file(file_info.file_path)
        
        text = await transcribe_voice(voice_bytes.read())
        if not text:
            await status_msg.edit_text("❌ Не удалось распознать голос.")
            return
            
        await status_msg.edit_text(f"🗣 <i>«{text}»</i>", parse_mode="HTML") # Добавил parse_mode
        
        res = await process_ai_message(text, message.chat.id)
        if res.get("type") == "alert_created":
            alerts = res.get("alerts", [])
            msg = "✅ <b>Созданы алерты:</b>\n"
            for a in alerts:
                msg += f"• #{a['id']} <b>{a['symbol']}</b> на уровне <code>{a['price']:.2f}</code> ({a['note']})\n"
            await message.answer(msg, parse_mode="HTML")
        else:
            await message.answer(res.get("text", "Принято."), parse_mode="HTML") # Добавил parse_mode
    except Exception as e:
        logging.error(f"Ошибка голосового ввода: {e}")
        await status_msg.edit_text("❌ Ошибка при обработке голосового сообщения.")

@router.message()
async def handle_all_messages(message: Message):
    if not message.text:
        return
    res = await process_ai_message(message.text, message.chat.id)
    if res.get("type") == "alert_created":
        alerts = res.get("alerts", [])
        msg = "✅ <b>Созданы алерты:</b>\n"
        for a in alerts:
            msg += f"• #{a['id']} <b>{a['symbol']}</b> на уровне <code>{a['price']:.2f}</code> ({a['note']})\n"
        await message.answer(msg, parse_mode="HTML")
    else:
        await message.answer(res.get("text", "Принято."), parse_mode="HTML")
