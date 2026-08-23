import logging
from datetime import datetime, timezone
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from core.bingx.candles import fetch_bingx_candles
from core.patterns import analyze_patterns
from core.formatter import format_report, clean_symbol, MSK_TZ
from core.database import get_all_alerts, clear_all_alerts, delete_alert, set_alert_recurring
from core.ai_intent import format_alerts_list
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

async def scan_timeframe(tf: str) -> list:
    """Сканирует один таймфрейм. Возвращает список сигналов."""
    signals = []
    # Уменьшаем лимит до 300 для скорости (для BB нужно 200, берем с запасом)
    limit = 300 
    
    logger.info(f"🚀 Старт скана {tf}...")
    
    for sym_full in SYMBOLS:
        try:
            klines = await fetch_bingx_candles(sym_full, tf=tf, limit=limit)
            
            if klines is None or klines.empty or len(klines) < 50:
                continue

            candles_list = klines.to_dict('records')
            pat_data = analyze_patterns(candles_list)
            
            if pat_data and pat_data.get("pattern") and pat_data["pattern"] != "-":
                last_closed_candle = klines.iloc[-1]
                # Безопасное время
                time_val = last_closed_candle.get('time') or last_closed_candle.get('timestamp') or last_closed_candle.get('open_time')
                # Безопасная конвертация времени (учитываем pandas Timestamp)
                if isinstance(time_val, int):
                    ts = time_val
                elif hasattr(time_val, 'timestamp'): # pandas Timestamp
                    ts = int(time_val.timestamp() * 1000)
                else:
                    ts = int(float(time_val)) if time_val else int(datetime.now().timestamp() * 1000)
                
                signals.append({
                    "symbol": clean_symbol(sym_full),
                    "tf": tf,
                    "pattern": pat_data["pattern"],
                    "direction_bb": pat_data.get("direction_bb", '⚪⚪⚪'),
                    "state_emoji": pat_data.get("state_emoji", ''),
                    "bb_breakthrough": pat_data.get("bb_breakthrough", ''),
                    "is_auto": False,
                    "timestamp": ts
                })
                logger.info(f"✅ {sym_full} ({tf}): {pat_data['pattern']}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка {sym_full} {tf}: {e}")
            
    return signals

@router.message(Command("scan"))
async def cmd_scan_all(message: Message):
    status_msg = await message.answer("🔍 Запуск полного сканирования (1w, 1d, 4h, 1h)... Это займет ~30 сек.")
    
    all_signals = []
    tfs = ["1w", "1d", "4h", "1h"]
    
    for tf in tfs:
        signals = await scan_timeframe(tf)
        all_signals.extend(signals)

    now_msk = datetime.now(MSK_TZ)
    report_text = format_report(all_signals, is_auto=False, now_dt=now_msk)
    
    if all_signals:
        await status_msg.edit_text(report_text, parse_mode="HTML")
    else:
        await status_msg.edit_text("✅ Паттернов не найдено на всех таймфреймах.", parse_mode="HTML")

@router.message(Command("scan_1h"))
async def cmd_scan_1h(message: Message):
    await run_scan_single(message, "1h")

@router.message(Command("scan_4h"))
async def cmd_scan_4h(message: Message):
    await run_scan_single(message, "4h")

@router.message(Command("scan_1d"))
async def cmd_scan_1d(message: Message):
    await run_scan_single(message, "1d")

@router.message(Command("scan_1w"))
async def cmd_scan_1w(message: Message):
    await run_scan_single(message, "1w")

async def run_scan_single(message: Message, tf: str):
    # Сначала отправляем сообщение, чтобы пользователь видел реакцию
    status_msg = await message.answer(f"🔍 Сканирую {tf}... Пожалуйста, подождите (~10 сек).")
    
    all_signals = await scan_timeframe(tf)
    now_msk = datetime.now(MSK_TZ)
    report_text = format_report(all_signals, is_auto=False, now_dt=now_msk)
    
    if all_signals:
        await status_msg.edit_text(report_text, parse_mode="HTML")
    else:
        await status_msg.edit_text(f"✅ По таймфрейму {tf.upper()} паттернов не найдено.", parse_mode="HTML")

@router.message(Command("alerts"))
async def cmd_alerts(message: Message):
    chat_id = message.chat.id
    alerts = get_all_alerts(chat_id)
    
    if not alerts:
        await message.answer("📭 У вас нет активных алертов.")
        return
    
    lines = ["🔔 <b>Ваши активные алерты:</b>\n", "<code>ID | АКТ | ЦЕНА | УСЛОВИЕ | ЗАМЕТКА</code>", "-" * 50]
    keyboard_buttons = []
    
    for a in alerts:
        aid = a['id']
        sym = clean_symbol(a['symbol'])
        price = f"{a['target_price']:.2f}"
        cond = a['condition'] or "CROSS"
        note = (a['note'] or "")[:15]
        lines.append(f"{aid:<3}| {sym:<4}| {price:<7}| {cond:<8}| {note}")
        keyboard_buttons.append([InlineKeyboardButton(text=f"❌ #{aid}", callback_data=f"del_alert_{aid}")])
    
    keyboard_buttons.append([InlineKeyboardButton(text="🗑 Удалить ВСЕ", callback_data="del_all_alerts")])
    
    text = "\n".join(lines) + "</code>"
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer(text, parse_mode="HTML", reply_markup=reply_markup)

@router.message(Command("del_all"))
async def cmd_del_all(message: Message):
    clear_all_alerts(message.chat.id)
    await message.answer("🗑 Все алерты удалены.")

@router.message(Command("price"))
async def cmd_price(message: Message):
    args = message.text.split()[1:]
    if not args:
        await message.answer("💰 Использование: /price BTC")
        return
    symbol = args[0].upper()
    # Простая маппинг
    if "BTC" in symbol: sym = "BTC-USDT"
    elif "ETH" in symbol: sym = "ETH-USDT"
    elif "SOL" in symbol: sym = "SOL-USDT"
    elif "KAS" in symbol: sym = "KAS-USDT"
    else: sym = f"{symbol}-USDT"
    
    try:
        from core.fetcher import get_ticker_price
        price = await get_ticker_price(sym)
        if price > 0:
            await message.answer(f"💰 {symbol}: {price:.2f}$")
        else:
            await message.answer("❌ Нет данных о цене.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.callback_query(F.data.startswith("del_alert_"))
async def callback_del_alert(callback_query):
    alert_id = int(callback_query.data.split("_")[2])
    delete_alert(alert_id, chat_id=callback_query.message.chat.id)
    await callback_query.answer("Удалено!", show_alert=True)
    # Перезагружаем список
    await cmd_alerts(callback_query.message)

@router.callback_query(F.data == "del_all_alerts")
async def callback_del_all(callback_query):
    clear_all_alerts(callback_query.message.chat.id)
    await callback_query.answer("Все удалено!", show_alert=True)
    await callback_query.message.edit_text("🗑 Все алерты удалены.")

@router.callback_query(F.data.startswith("set_recurring_"))
async def callback_set_recurring(callback_query):
    alert_id = int(callback_query.data.split("_")[2])
    set_alert_recurring(alert_id, True)
    await callback_query.answer("Теперь многоразовый!", show_alert=True)
    await callback_query.message.delete()

@router.message()
async def handle_ai_messages(message: Message):
    text = message.text
    if not text or text.startswith("/"):
        return
    from core.ai_intent import process_ai_command
    result = await process_ai_command(text, message.chat.id)
    if result["type"] != "ignore":
        await message.answer(result["message"], parse_mode="HTML")
