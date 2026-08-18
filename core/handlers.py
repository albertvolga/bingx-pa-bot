import logging
import datetime
import pandas as pd
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ContentType
from aiogram.filters import Command

from core.database import delete_alert, get_all_alerts, clear_all_alerts
from core.ai_handler import process_ai_message, format_alerts_table, clean_symbol
from core.bingx import fetch_bingx_candles
from core.patterns import analyze_patterns
from core.stt import transcribe_voice
from core.formatter import format_report # Импортируем новую функцию форматирования

router = Router()

def register_custom_handlers(dp, bot=None):
    dp.include_router(router)

# Список символов для сканирования - теперь можно расширить или брать извне
SCAN_SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "DOT-USDT", "PAXG-USDT", "SILVER-USDT", "DOGE-USDT", "ADA-USDT", "LTC-USDT"]

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

async def run_scan(message: Message, interval: str = "all"):
    """
    Запускает сканирование паттернов для ручных команд /scan.
    Анализирует ПОСЛЕДНИЙ ЗАКРЫТЫЙ бар.
    """
    now_dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)
    tf_title = "Все ТФ" if interval == "all" else interval
    status_text = f"🔍 Запускаю сканирование {tf_title} ({now_dt.strftime('%d.%m.%y %H:%M')} МСК)..."

    status_msg = await message.answer(status_text)

    # Включаем 1w для ручного сканирования, если это не конкретный ТФ
    timeframes = ["1h", "4h", "1d", "1w"] if interval == "all" else [interval]
    all_signals = []

    for sym in SCAN_SYMBOLS:
        for tf in timeframes:
            try:
                # Для ручного сканирования берем достаточно свечей для анализа паттернов
                # analyze_patterns смотрит на последние 3 свечи, поэтому limit=3 будет достаточно,
                # но для более надежного обнаружения, скажем, 5-7. Возьмем 10 на всякий случай.
                klines = await fetch_bingx_candles(sym, timeframe=tf, limit=10, interval=tf)
                if not klines or len(klines) < 3: # Для анализа нужно мин 3
                    continue

                df = pd.DataFrame(klines)
                
                # analyze_patterns работает с DataFrame и возвращает паттерн для последнего ЗАКРЫТОГО бара
                # BingX API (fetch_bingx_candles) возвращает уже закрытые свечи. Последняя в списке - это последний закрытый бар.
                pat_found = analyze_patterns(df) 

                if pat_found != "-": # Если паттерн найден
                    last_closed_candle = df.iloc[-1] 
                    direction = "bull" if last_closed_candle['close'] >= last_closed_candle['open'] else "bear"
                    
                    all_signals.append({
                        "symbol": clean_symbol(sym),
                        "tf": tf,
                        "pattern": pat_found,
                        "direction": direction,
                        "is_auto": False, # Это ручной скан
                        "timestamp": last_closed_candle['time'] # Для отображения времени открытия последнего закрытого бара
                    })
            except Exception as e:
                logging.error(f"Ошибка сканирования {sym} {tf}: {e}")

    report_text = format_report(all_signals, is_auto=False, now_dt=now_dt)
    
    await status_msg.edit_text(report_text, parse_mode="HTML")

@router.message(Command("alerts"))
async def cmd_alerts(message: Message):
    text, buttons = format_alerts_table(chat_id=message.chat.id)
    keyboard = build_compact_keyboard(buttons, row_width=4) if buttons else None
    await message.answer(text, reply_markup=keyboard)

@router.message(Command("del_all"))
async def cmd_del_all(message: Message):
    clear_all_alerts(message.chat.id)
    await message.answer("🗑 Все активные алерты успешно удалены!")

@router.message(Command("scan"))
async def cmd_scan_all(message: Message): await run_scan(message, "all", is_auto=False)

@router.message(Command("scan_1h"))
async def cmd_scan_1h(message: Message): await run_scan(message, "1h", is_auto=False)

@router.message(Command("scan_4h"))
async def cmd_scan_4h(message: Message): await run_scan(message, "4h", is_auto=False)

@router.message(Command("scan_1d"))
async def cmd_scan_1d(message: Message): await run_scan(message, "1d", is_auto=False)

@router.message(Command("scan_1w"))
async def cmd_scan_1w(message: Message): await run_scan(message, "1w", is_auto=False)

@router.callback_query(F.data.startswith("del_alert_"))
async def process_del_alert(callback: CallbackQuery):
    alert_id = int(callback.data.split("_")[2])
    delete_alert(alert_id)
    await callback.answer("Алерт удален!")
    
    text, buttons = format_alerts_table(chat_id=callback.message.chat.id)
    keyboard = build_compact_keyboard(buttons, row_width=4) if buttons else None
    
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        pass

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
            
        await status_msg.edit_text(f"🗣 <i>«{text}»</i>")
        
        res = await process_ai_message(text, message.chat.id)
        if res.get("type") == "alert_created":
            alerts = res.get("alerts", [])
            msg = "✅ <b>Созданы алерты:</b>\n"
            for a in alerts:
                msg += f"• #{a['id']} <b>{a['symbol']}</b> на уровне <code>{a['price']}</code> ({a['note']})\n"
            await message.answer(msg)
        else:
            await message.answer(res.get("text", "Принято."))
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
            msg += f"• #{a['id']} <b>{a['symbol']}</b> на уровне <code>{a['price']}</code> ({a['note']})\n"
        await message.answer(msg)
    else:
        await message.answer(res.get("text", "Принято."))
