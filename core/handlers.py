import logging
import datetime
import pandas as pd
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ContentType
from aiogram.filters import Command
from datetime import datetime, timezone # Import datetime and timezone

from core.database import delete_alert, get_all_alerts, clear_all_alerts, set_alert_recurring
from core.ai_handler import process_ai_message, clean_symbol
from core.bingx.candles import fetch_bingx_candles, get_all_usdt_pairs
from core.patterns import analyze_patterns
from core.stt import transcribe_voice
from core.formatter import format_report, format_alerts_table
from config import SYMBOL_MAP, MSK_TZ # Import MSK_TZ from config (or main if moved there)

router = Router()

def register_custom_handlers(dp, bot=None):
    dp.include_router(router)

# Список символов для сканирования: теперь берем из конфига
# SCAN_SYMBOLS будет использоваться как полный список для /scan
# Для автоотчета берется get_all_usdt_pairs()

@router.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "📚 <b>Справка по командам и обозначениям:</b>\n\n"
        "<b>Общие команды:</b>\n"
        "▫️ <code>/start</code> — Приветствие и краткий список команд.\n"
        "▫️ <code>/help</code> — Эта справка.\n"
        "▫️ <code>/list</code> — Показать все отслеживаемые активы и таймфреймы.\n"
        "▫️ <code>/status</code> — Проверить статус работы бота.\n\n"
        "<b>Сканирование рынка:</b>\n"
        "▫️ <code>/scan</code> — Ручное сканирование всех ТФ. \n"
        "   Например: <code>/scan</code> (сейчас) или <code>/scan 15.08 10:00</code> (исторический скан).\n"
        "▫️ <code>/scan_1h</code>, <code>/scan_4h</code>, <code>/scan_1d</code>, <code>/scan_1w</code> — Ручное сканирование конкретного ТФ.\n\n"
        "<b>Управление алертами:</b>\n"
        "▫️ <code>/alerts</code> — Показать все ваши активные алерты.\n"
        "▫️ <code>/del_all</code> — Удалить ВСЕ ваши активные алерты.\n"
        "▫️ <b>Создание алерта голосом или текстом:</b>\n"
        "   Например: <i>«Поставь алерт на KAS на 0.1249»</i>\n"
        "   Или: <i>«Когда Эфир пробьет хай вчерашней дневной свечи?»</i>\n"
        "   Или: <i>«Алерт на ADA по лоу 4-часовой свечи закрытой в 10:00»</i>\n\n"
        "<b>Эмодзи в отчётах:</b>\n"
        "▫️ <code>🟡🟡🟡</code> — Направление тренда по BB: сильное восходящее.\n"
        "▫️ <code>🔴🔴🔴</code> — Направление тренда по BB: сильное нисходящее.\n"
        "▫️ <code>⚪⚪⚪</code> — Направление тренда по BB: флэт или смешанное.\n"
        "▫️ <code>☀️</code> — Состояние свечи: <code>Squeeze</code> (сужение волатильности).\n"
        "▫️ <code>💥</code> — Состояние свечи: <code>Expansion</code> (расширение волатильности).\n"
        "▫️ <code>🔷</code> — Состояние свечи: <code>Squat</code> (узкое тело при потенциально большом объеме - текущая заглушка без анализа объема).\n"
    )
    await message.answer(help_text, parse_mode="HTML")

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
    
    # Определяем текущее время для отображения, если не исторический скан
    current_time_display = now_msk.strftime('%d.%m.%y %H:%M')

    if is_historical_scan:
        # scan_datetime в данном случае уже в UTC, как его отправит API.
        # Для отображения пользователю конвертируем в MSK
        display_time = (scan_datetime + datetime.timedelta(hours=3)).strftime('%d.%m.%y %H:%M') 
        tf_title = "Все ТФ" if interval == "all" else interval
        status_text = f"🔍 Запускаю историческое сканирование {tf_title} на {display_time} МСК..."
    else:
        tf_title = "Все ТФ" if interval == "all" else interval
        status_text = f"🔍 Запускаю сканирование {tf_title} ({current_time_display} МСК)..."

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

                # BingX API `fetch_bingx_candles` возвращает *закрытые* свечи.
                # Если `end_time_ms` указан, то последняя свеча в `klines` будет последней *закрытой* до или в `end_time_ms`.
                klines = await fetch_bingx_candles(
                    symbol=sym_full, 
                    timeframe=tf, 
                    limit=limit_needed, 
                    # Если исторический скан, указываем endTime (оно уже в UTC)
                    end_time_ms=int(scan_datetime.timestamp() * 1000) if is_historical_scan else None
                )
                
                if not klines or len(klines) < 3: 
                    logging.warning(f"Недостаточно данных для {sym_full} {tf} при сканировании.")
                    continue

                df = pd.DataFrame(klines)
                
                # Для ручного сканирования всегда анализируем последнюю *закрытую* свечу в df.
                # analyze_patterns будет работать с df.iloc[-1] для однобарных паттернов
                # и с более ранними для многобарных.
                
                pat_data = analyze_patterns(df) # analyze_patterns теперь возвращает dict
                
                if pat_data and pat_data["pattern"] != "-": 
                    last_analyzed_candle = df.iloc[-1] # Последняя *закрытая* свеча
                    direction_bb = pat_data.get("direction_bb", '⚪⚪⚪') 
                    state_emoji = pat_data.get("state_emoji", '') 
                    
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
    
    # Define now_msk here for correct usage within the function scope
    now_msk = datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)

    if len(args) > 1:
        # Пробуем распарсить дату и время
        try:
            # Ожидаем формат типа "ДД.ММ ЧЧ:ММ" или "ДД.ММ"
            date_time_str = " ".join(args[1:])
            
            parsed_dt = None
            # Пробуем полный формат "ДД.ММ ЧЧ:ММ"
            try:
                parsed_dt = datetime.strptime(date_time_str, "%d.%m %H:%M")
            except ValueError:
                # Если только дата "ДД.ММ", устанавливаем время по умолчанию 03:00 (время закрытия дневной свечи по MSK)
                parsed_dt = datetime.strptime(date_time_str, "%d.%m").replace(hour=3, minute=0)
            
            # Устанавливаем год в текущий, если не указан, и добавляем часовой пояс MSK
            # BingX API работает с timestamp в UTC, поэтому конвертируем.
            # Мы хотим запросить данные *до* определенного времени MSK.
            # Устанавливаем год в текущий, если не указан, и добавляем часовой пояс MSK
            # Затем конвертируем в UTC для BingX API.
            # Если пользователь ввел "15.08 10:00", это 10:00 MSK.
            # Нам нужно, чтобы BingX API вернул свечи, *закрытые до* 10:00 MSK (которое 07:00 UTC).
            parsed_dt = parsed_dt.replace(year=now_msk.year) # Устанавливаем год

            # Создаем naive datetime object и делаем его aware в MSK
            local_dt_msk = MSK_TZ.localize(parsed_dt)
            # Конвертируем в UTC
            scan_dt_utc = local_dt_msk.astimezone(timezone.utc)
            
            scan_dt = scan_dt_utc # The scan_datetime passed to run_scan should be in UTC
            
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
    # Убеждаемся, что мы отвечаем на коллбек до того, как пытаемся редактировать сообщение.
    await callback.answer("Алерт удален!")
    
    alerts_list = get_all_alerts(chat_id=callback.message.chat.id)
    text, buttons = format_alerts_table(alerts_list)
    keyboard = build_compact_keyboard(buttons, row_width=4) if buttons else None
    
    try:
        # Если алертов больше нет, убираем reply_markup полностью, чтобы не висели старые кнопки
        if not alerts_list:
            await callback.message.edit_text(text, reply_markup=None, parse_mode="HTML")
        else:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logging.warning(f"Ошибка при обновлении сообщения после удаления алерта: {e}")
        # Если редактирование не удалось (например, сообщение слишком старое или без кнопок),
        # отправляем новое сообщение с обновленным списком.
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML") 

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
