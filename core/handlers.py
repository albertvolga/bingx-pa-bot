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

router = Router()

def register_custom_handlers(dp, bot=None):
    dp.include_router(router)

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

def calculate_bar_close_time(ts_ms: float, tf: str) -> str:
    """Вычисляет точное время ЗАКРЫТИЯ свечи по ее метке времени открытия"""
    if ts_ms <= 0:
        return "12:00"
    dt_open = datetime.datetime.fromtimestamp(ts_ms / 1000, tz=datetime.timezone.utc) + datetime.timedelta(hours=3)
    
    if tf == "15m":
        dt_close = dt_open + datetime.timedelta(minutes=15)
    elif tf == "1h":
        dt_close = dt_open + datetime.timedelta(hours=1)
    elif tf == "4h":
        dt_close = dt_open + datetime.timedelta(hours=4)
    elif tf in ["1d", "1w"]:
        dt_close = dt_open + datetime.timedelta(days=1)
    else:
        dt_close = dt_open
        
    return dt_close.strftime("%H:%M")

async def run_scan(message: Message, interval: str = "all", is_auto: bool = False):
    now_dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)
    now_str = now_dt.strftime("%d.%m.%2y %H:%M")
    
    if is_auto:
        title_name = f"АвтоОтчёт на {now_str} МСК"
        status_text = f"🔍 Запускаю автоотчет ({now_str} МСК)..."
    else:
        tf_title = "Все ТФ" if interval == "all" else interval
        title_name = f"Сканирование {tf_title} ({now_str} МСК)"
        status_text = f"🔍 Запускаю сканирование {tf_title}..."

    # Отправляем временное статусное сообщение
    status_msg = await message.answer(status_text)

    timeframes = ["1h", "4h", "1d"] if interval == "all" else [interval]
    rows = []

    for sym in SCAN_SYMBOLS:
        clean_name = sym.replace("-USDT", "").replace("SILVER", "XAG").replace("PAXG", "XAU")[:4]
        
        for tf in timeframes:
            try:
                klines = await fetch_bingx_candles(sym, timeframe=tf, limit=30, interval=tf)
                if not klines or len(klines) < 22:
                    continue

                df = pd.DataFrame(klines)
                last_closed = df.iloc[-2]
                
                # Получаем точное время ЗАКРЫТИЯ свечи
                ts = float(last_closed.get("time", last_closed.get("timestamp", 0)))
                time_str = calculate_bar_close_time(ts, tf)

                pat, dir_icon, state_icon = analyze_patterns(df)

                rows.append({
                    "act": clean_name,
                    "time": time_str,
                    "tf": tf,
                    "dir": dir_icon,
                    "pat": pat,
                    "state": state_icon
                })
            except Exception as e:
                logging.error(f"Ошибка сканирования {sym} {tf}: {e}")

    if not rows:
        await status_msg.edit_text("⚠️ Не удалось сформировать отчет.")
        return

    table_text = f"📊 <b>{title_name}:</b>\n\n<pre>"
    table_text += f"{'АКТ':<4} | {'ВРЕМЯ':<5} | {'ТФ':<3} | {'НАПР'} | {'ПАТ':<7} | {'СОСТ'}\n"
    table_text += "-" * 38 + "\n"

    for r in rows:
        table_text += f"{r['act']:<4} | {r['time']:<5} | {r['tf']:<3} |  {r['dir']}   | {r['pat']:<7} | {r['state']}\n"

    table_text += "</pre>"
    
    # Редактируем временное сообщение, чтобы оно не оставалось висеть!
    await status_msg.edit_text(table_text)

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
