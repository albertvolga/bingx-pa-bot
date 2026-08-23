import logging
from datetime import datetime, timezone, timedelta
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command

from core.bingx.candles import fetch_bingx_candles
from core.patterns import analyze_patterns
from core.formatter import format_report, clean_symbol, MSK_TZ
from core.database import get_all_alerts, clear_all_alerts, delete_alert, set_alert_recurring
from core.ai_intent import process_ai_command, format_alerts_list
from config import SYMBOL_MAP

logger = logging.getLogger(__name__)

router = Router()

SYMBOLS = [
    "BTC-USDT", "ETH-USDT", "SOL-USDT", "LTC-USDT", 
    "ADA-USDT", "DOT-USDT", "ATOM-USDT", "XRP-USDT", 
    "DOGE-USDT", "KAS-USDT", "XAU-USDT", "XAG-USDT"
]

def register_custom_handlers(dp, bot=None):
    dp.include_router(router)
    # Устанавливаем главное меню при старте
    if bot:
        import asyncio
        asyncio.create_task(set_main_menu(bot))

async def set_main_menu(bot):
    """Устанавливает кнопки меню для всех пользователей."""
    kb = [
        [KeyboardButton(text="📊 Скан 1H"), KeyboardButton(text="📊 Скан 4H")],
        [KeyboardButton(text="📊 Скан 1D"), KeyboardButton(text="📊 Скан 1W")],
        [KeyboardButton(text="🔔 Мои алерты"), KeyboardButton(text="🗑 Удалить все")],
        [KeyboardButton(text="🔄 Перезапустить бота")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, input_field_placeholder="Выберите действие или напишите текстом...")
    await bot.set_my_commands([]) # Отключаем стандартные команды, чтобы показывались только кнопки
    # Примечание: set_my_commands меняет список команд в слэш-меню, а кнопки клавиатуры отправляются пользователю
    # Для глобальной установки кнопок нужно отправлять их первым сообщением или использовать set_my_commands для слэшей
    
async def send_main_keyboard(chat_id):
    """Отправляет клавиатуру с основными кнопками."""
    kb = [
        [KeyboardButton(text="📊 Скан 1H"), KeyboardButton(text="📊 Скан 4H")],
        [KeyboardButton(text="📊 Скан 1D"), KeyboardButton(text="📊 Скан 1W")],
        [KeyboardButton(text="🔔 Мои алерты"), KeyboardButton(text="🗑 Удалить все")],
        [KeyboardButton(text="🔄 Перезапустить бота")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    # Эта функция вызывается внутри хендлеров, если нужно принудительно показать меню

async def scan_timeframe(tf: str, message: Message, status_msg: Message) -> list:
    signals = []
    now_msk = datetime.now(MSK_TZ)
    
    for sym_full in SYMBOLS:
        try:
            klines = await fetch_bingx_candles(sym_full, tf=tf, limit=600)
            if klines is None or klines.empty or len(klines) < 30:
                continue
            candles_list = klines.to_dict('records')
            pat_data = analyze_patterns(candles_list)
            
            if pat_data and pat_data.get("pattern") and pat_data["pattern"] != "-": 
                last_closed_candle = klines.iloc[-1]
                signals.append({
                    "symbol": clean_symbol(sym_full),
                    "tf": tf,
                    "pattern": pat_data["pattern"],
                    "direction_bb": pat_data.get("direction_bb", '⚪⚪⚪'),
                    "state_emoji": pat_data.get("state_emoji", ''),
                    "bb_breakthrough": pat_data.get("bb_breakthrough", ''),
                    "is_auto": False,
                    "timestamp": last_closed_candle['time']
                })
        except Exception as e:
            logger.error(f"Ошибка сканирования {sym_full} {tf}: {e}")
    return signals

@router.message(Command("start"))
async def cmd_start(message: Message):
    kb = [
        [KeyboardButton(text="📊 Скан 1H"), KeyboardButton(text="📊 Скан 4H")],
        [KeyboardButton(text="📊 Скан 1D"), KeyboardButton(text="📊 Скан 1W")],
        [KeyboardButton(text="🔔 Мои алерты"), KeyboardButton(text="🗑 Удалить все")],
        [KeyboardButton(text="🔄 Перезапустить бота")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.answer(
        "👋 <b>Бот запущен!</b>\n\n"
        "Я умею:\n"
        "• Сканировать рынок по таймфреймам\n"
        "• Ставить алерты по голосу/тексту (например: <i>'поставь алерт на биткоин на хай вчерашнего дня'</i>)\n"
        "• Управлять алертами через кнопки\n\n"
        "Выберите действие в меню:",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.message(F.text == "📊 Скан 1H")
async def btn_scan_1h(message: Message):
    await run_scan_for_tf(message, "1h")

@router.message(F.text == "📊 Скан 4H")
async def btn_scan_4h(message: Message):
    await run_scan_for_tf(message, "4h")

@router.message(F.text == "📊 Скан 1D")
async def btn_scan_1d(message: Message):
    await run_scan_for_tf(message, "1d")

@router.message(F.text == "📊 Скан 1W")
async def btn_scan_1w(message: Message):
    await run_scan_for_tf(message, "1w")

async def run_scan_for_tf(message: Message, tf: str):
    now_msk = datetime.now(MSK_TZ)
    status_msg = await message.answer(f"🔍 Сканирую рынок ({tf})...")
    all_signals = await scan_timeframe(tf, message, status_msg)
    report_text = format_report(all_signals, is_auto=False, now_dt=now_msk)
    if all_signals:
        await status_msg.edit_text(report_text, parse_mode="HTML")
    else:
        await status_msg.edit_text(f"✅ По таймфрейму {tf.upper()} интересных паттернов не найдено.")

@router.message(F.text == "🔔 Мои алерты")
async def btn_alerts(message: Message):
    chat_id = message.chat.id
    alerts = get_all_alerts(chat_id)
    if not alerts:
        await message.answer("📭 У вас нет активных алертов.")
        return
    
    lines = ["🔔 <b>Ваши активные алерты:</b>\n", "<code>ID | АКТ  | ЦЕНА     | УСЛОВИЕ      | ЗАМЕТКА</code>", "-" * 65]
    keyboard_buttons = []
    
    for a in alerts:
        aid = a['id']
        sym = clean_symbol(a['symbol'])
        price = f"{a['target_price']:.2f}"
        cond = a['condition'] or "CROSS"
        note = (a['note'] or "")[:25]
        lines.append(f"{aid:<3}| {sym:<5}| {price:<9}| {cond:<12}| {note}")
        keyboard_buttons.append([InlineKeyboardButton(text=f"❌ Удалить #{aid} ({sym})", callback_data=f"del_alert_{aid}")])
    
    keyboard_buttons.append([InlineKeyboardButton(text="🗑 Удалить ВСЕ алерты", callback_data="del_all_alerts")])
    
    text = "\n".join(lines) + "</code>"
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer(text, parse_mode="HTML", reply_markup=reply_markup)

@router.message(F.text == "🗑 Удалить все")
async def btn_del_all(message: Message):
    chat_id = message.chat.id
    clear_all_alerts(chat_id)
    await message.answer("🗑 Все ваши алерты удалены.")

@router.message(F.text == "🔄 Перезапустить бота")
async def btn_restart(message: Message):
    await message.answer("🔄 <b>Перезагрузка бота...</b>\nПодождите 5 секунд.", parse_mode="HTML")
    import os, sys, time
    # Планируем перезапуск процесса
    pid = os.getpid()
    # Используем простой способ: убиваем себя, а systemd или cron перезапустит
    # Или просто выходим, если есть внешний монитор
    await message.answer("✅ Бот перезагружается. Я вернусь через несколько секунд.", parse_mode="HTML")
    time.sleep(2)
    os.kill(pid, 9) # Убиваем процесс

@router.callback_query(F.data.startswith("del_alert_"))
async def callback_del_alert(callback_query):
    alert_id = int(callback_query.data.split("_")[2])
    chat_id = callback_query.message.chat.id
    delete_alert(alert_id, chat_id=chat_id)
    await callback_query.answer(f"✅ Алерт #{alert_id} удален!", show_alert=True)
    # Обновляем список
    alerts = get_all_alerts(chat_id)
    if not alerts:
        await callback_query.message.edit_text("📭 У вас нет активных алертов.")
        return
    
    lines = ["🔔 <b>Ваши активные алерты:</b>\n", "<code>ID | АКТ  | ЦЕНА     | УСЛОВИЕ      | ЗАМЕТКА</code>", "-" * 65]
    keyboard_buttons = []
    for a in alerts:
        aid = a['id']
        sym = clean_symbol(a['symbol'])
        price = f"{a['target_price']:.2f}"
        cond = a['condition'] or "CROSS"
        note = (a['note'] or "")[:25]
        lines.append(f"{aid:<3}| {sym:<5}| {price:<9}| {cond:<12}| {note}")
        keyboard_buttons.append([InlineKeyboardButton(text=f"❌ Удалить #{aid} ({sym})", callback_data=f"del_alert_{aid}")])
    keyboard_buttons.append([InlineKeyboardButton(text="🗑 Удалить ВСЕ алерты", callback_data="del_all_alerts")])
    text = "\n".join(lines) + "</code>"
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)

@router.callback_query(F.data == "del_all_alerts")
async def callback_del_all(callback_query):
    chat_id = callback_query.message.chat.id
    clear_all_alerts(chat_id)
    await callback_query.answer("🗑 Все алерты удалены!", show_alert=True)
    await callback_query.message.edit_text("🗑 Все ваши алерты удалены.")

@router.callback_query(F.data.startswith("set_recurring_"))
async def callback_set_recurring(callback_query):
    alert_id = int(callback_query.data.split("_")[2])
    set_alert_recurring(alert_id, True)
    await callback_query.answer(f"✅ Алерт #{alert_id} теперь многоразовый!", show_alert=True)
    await callback_query.message.delete()

@router.message()
async def handle_ai_messages(message: Message):
    text = message.text
    if not text:
        # Если это не текст (например, голосовое), игнорируем или просим текст
        if message.voice:
            await message.answer("🎤 <b>Голосовые сообщения пока не поддерживаются.</b>\nПожалуйста, напишите текстом: <i>'поставь алерт на биткоин...'</i>", parse_mode="HTML")
        return
        
    if text.startswith("/"):
        return
        
    chat_id = message.chat.id
    result = await process_ai_command(text, chat_id)
    
    if result["type"] == "ignore":
        return
        
    if result["type"] == "error":
        await message.answer(result["message"], parse_mode="HTML")
    elif result["type"] == "success":
        await message.answer(result["message"], parse_mode="HTML")
