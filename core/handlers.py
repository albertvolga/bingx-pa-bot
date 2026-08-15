import datetime
import logging
import re
import pandas as pd
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, ContentType, InlineKeyboardButton, InlineKeyboardMarkup

from core.fetcher import fetch_klines, SCAN_SYMBOLS
from core.patterns import analyze_patterns
from core.formatter import format_table_report, format_alerts_table, build_compact_keyboard
from core.database import clear_all_alerts, delete_alert, add_alert, get_user_alerts
from core.stt import transcribe_voice

router = Router()

HELP_TEXT = """
📖 <b>Справка по использованию бота BingX Price Action</b>

<b>Основные команды:</b>
• /scan — Полное сканирование всех ТФ (1H, 4H, 1D)
• /alert [СИМВОЛ] [ТФ] [ПАТТЕРН] — Установить алерт (напр: <code>/alert BTC 1h Pin</code>)
• /alerts — Посмотреть и удалить мои алерты
• /del_all — Очистка всех моих алертов
• /help — Справка
"""

# Словарь синонимов монет
SYMBOL_ALIASES = {
    "BTC": ["btc", "биткоин", "биток", "btc usdt"],
    "ETH": ["eth", "эфир", "эфириум", "кефир", "eth usdt"],
    "SOL": ["sol", "солана", "соляна", "sol usdt"],
    "XRP": ["xrp", "рипл", "риппл", "хрп"],
    "BNB": ["bnb", "бнб", "бинанс"],
    "DOGE": ["doge", "доги", "доге", "собаки"],
    "ADA": ["ada", "ада", "кардано"]
}

async def run_scan(message, interval="all", is_auto=False):
    """Выполняет сканирование рынка и отправляет отчет"""
    try:
        title_prefix = "АвтоОтчёт" if is_auto else "Сканирование Все ТФ"
        now_str = datetime.datetime.now().strftime("%d.%m.%Y %H:%M MSK")
        
        results = []
        for symbol in SCAN_SYMBOLS:
            tf_list = ["1h", "4h", "1d"] if interval == "all" else [interval]
            for tf in tf_list:
                klines = await fetch_klines(symbol, interval=tf, limit=10)
                if klines and len(klines) >= 3:
                    df = pd.DataFrame(klines)
                    pats = analyze_patterns(df)
                    if pats:
                        results.append({
                            "symbol": symbol.replace("-USDT", "").replace("USDT", ""),
                            "time": datetime.datetime.now().strftime("%H:00"),
                            "tf": tf,
                            "patterns": pats
                        })
        
        text = format_table_report(results, f"{title_prefix} ({now_str})")
        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Ошибка в run_scan: {e}")
        if not is_auto:
            await message.answer("❌ Произошла ошибка при сканировании рынка.")

def parse_alert_intent(text: str):
    """Парсит текст или голос с учетом синонимов монет и ТФ"""
    text_clean = text.lower()
    
    # 1. Поиск инструмента (Symbol)
    sym = "BTC"
    found_sym = False
    for ticker, aliases in SYMBOL_ALIASES.items():
        for alias in aliases:
            if alias in text_clean:
                sym = ticker
                found_sym = True
                break
        if found_sym:
            break
            
    if not found_sym:
        for s in SCAN_SYMBOLS:
            clean_s = s.replace("-USDT", "").replace("USDT", "").lower()
            if clean_s in text_clean:
                sym = clean_s.upper()
                break
            
    # 2. Поиск таймфрейма (Timeframe)
    tf = "1h"
    if any(x in text_clean for x in ["4h", "4ч", "4 часа", "четырехчасовой", "4-часовой"]):
        tf = "4h"
    elif any(x in text_clean for x in ["1d", "1д", "дневной", "дневка", "1 день"]):
        tf = "1d"
    elif any(x in text_clean for x in ["15m", "15м", "15 мин", "пятнадцатиминутный"]):
        tf = "15m"
        
    # 3. Поиск паттерна (Pattern)
    pat = "PIN"
    if any(x in text_clean for x in ["out", "внешн", "поглощ"]):
        pat = "OUT"
    elif any(x in text_clean for x in ["ins", "внутр", "inside"]):
        pat = "INS"
    elif "ppr" in text_clean:
        pat = "PPR"
    elif any(x in text_clean for x in ["fak", "ложн", "фейки"]):
        pat = "FAK"
        
    return sym, tf, pat

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT, parse_mode="HTML")

@router.message(Command("scan"))
async def cmd_scan_all(message: Message, command: CommandObject):
    await run_scan(message, "all", is_auto=False)

@router.message(Command("alert"))
async def cmd_add_alert(message: Message, command: CommandObject):
    if not command.args:
        await message.answer("⚠️ Формат: <code>/alert BTC 1h Pin</code>", parse_mode="HTML")
        return
    
    parts = command.args.strip().split()
    if len(parts) < 3:
        await message.answer("⚠️ Укажите символ, таймфрейм и паттерн. Пример: <code>/alert BTC 1h Pin</code>", parse_mode="HTML")
        return
        
    sym, tf, pat = parts[0].upper(), parts[1].lower(), parts[2].upper()
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="1️⃣ Одноразовый", callback_data=f"addalt_0_{sym}_{tf}_{pat}"),
        InlineKeyboardButton(text="🔄 Многоразовый", callback_data=f"addalt_1_{sym}_{tf}_{pat}")
    ]])
    await message.answer(f"🔔 Выберите тип алерта для <b>{sym} ({tf.upper()}) - {pat}</b>:", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("addalt_"))
async def process_add_alert_cb(callback: CallbackQuery):
    _, is_rep, sym, tf, pat = callback.data.split("_")
    is_repeating = bool(int(is_rep))
    add_alert(callback.message.chat.id, sym, tf, pat, is_repeating)
    tipo_str = "🔄 Многоразовый" if is_repeating else "1️⃣ Одноразовый"
    await callback.message.edit_text(f"✅ Установлен {tipo_str} алерт: <b>{sym} | {tf.upper()} | {pat}</b>", parse_mode="HTML")

@router.message(Command("alerts"))
async def cmd_list_alerts(message: Message):
    text, buttons = format_alerts_table(message.chat.id)
    kb = build_compact_keyboard(buttons, row_width=2) if buttons else None
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.message(Command("del_all"))
async def cmd_del_all(message: Message):
    clear_all_alerts(message.chat.id)
    await message.answer("🗑 Все ваши активные алерты успешно удалены!")

@router.callback_query(F.data.startswith("del_alert_"))
async def process_del_alert(callback: CallbackQuery):
    alert_id = int(callback.data.split("_")[2])
    delete_alert(alert_id, callback.message.chat.id)
    await callback.answer("Алерт удален!")
    
    text, buttons = format_alerts_table(callback.message.chat.id)
    kb = build_compact_keyboard(buttons, row_width=2) if buttons else None
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass

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
            
        sym, tf, pat = parse_alert_intent(text)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="1️⃣ Одноразовый", callback_data=f"addalt_0_{sym}_{tf}_{pat}"),
            InlineKeyboardButton(text="🔄 Многоразовый", callback_data=f"addalt_1_{sym}_{tf}_{pat}")
        ]])
        await status_msg.edit_text(
            f"🗣 <i>«{text}»</i>\n\n🔔 Найдена команда алерта: <b>{sym} ({tf.upper()}) - {pat}</b>. Выберите тип:",
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Ошибка распознавания голоса: {e}")
        await status_msg.edit_text("❌ Произошла ошибка при распознавании речи.")

@router.message(F.text & ~F.text.startswith("/"))
async def handle_text_message(message: Message):
    if any(w in message.text.lower() for w in ["алерт", "уведомлен", "постав", "напомни", "сигнал"]):
        sym, tf, pat = parse_alert_intent(message.text)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="1️⃣ Одноразовый", callback_data=f"addalt_0_{sym}_{tf}_{pat}"),
            InlineKeyboardButton(text="🔄 Многоразовый", callback_data=f"addalt_1_{sym}_{tf}_{pat}")
        ]])
        await message.answer(
            f"🔔 Найдена команда алерта: <b>{sym} ({tf.upper()}) - {pat}</b>. Выберите тип:",
            reply_markup=kb,
            parse_mode="HTML"
        )
