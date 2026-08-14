import logging
import datetime
import pandas as pd
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from core.database import delete_alert, get_all_alerts, clear_all_alerts
from core.ai_handler import process_ai_message, format_alerts_table, clean_symbol
from core.bingx import fetch_bingx_candles

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

def analyze_bar_patterns(df):
    """
    Анализ паттернов, SMA, направления и Сквот-бара
    """
    if len(df) < 21:
        return "-", "🟡", ""

    # Берем последнюю закрытую свечу (df.iloc[-2]) и предыдущие
    c1 = df.iloc[-2] # Закрытый бар
    c2 = df.iloc[-3] # Преддыдущий
    
    close_p = float(c1["close"])
    high_p = float(c1["high"])
    low_p = float(c1["low"])
    open_p = float(c1["open"])
    vol_p = float(c1.get("volume", 0))

    # SMA 20
    sma20 = df["close"].astype(float).tail(21).iloc[:-1].mean()
    direction = "🟡" if close_p >= sma20 else "🔴"

    # Динамика диапазонов
    r1 = high_p - low_p
    r2 = float(c2["high"]) - float(c2["low"])
    body = abs(close_p - open_p)

    pats = []
    
    # ППР / Overlap / Breakout
    if close_p > float(c2["high"]):
        pats.append("PPR")
    elif close_p < float(c2["low"]):
        pats.append("PPR")

    # Сжатие (Inside Bar) / Расширение (Outside Bar)
    if high_p < float(c2["high"]) and low_p > float(c2["low"]):
        pats.append("Ins")
    elif high_p > float(c2["high"]) and low_p < float(c2["low"]):
        pats.append("Out")

    # Pinsky / Fakey
    if body > 0 and (r1 / body) > 2.5:
        pats.append("Pin")

    pat_str = "/".join(pats) if pats else "-"

    # Сквот бар (Squat): Высокий объем при маленьком диапазоне свечи
    avg_vol = df["volume"].astype(float).tail(10).mean() if "volume" in df else 1
    is_squat = False
    if r1 > 0 and avg_vol > 0:
        eff = vol_p / r1
        if vol_p > avg_vol * 1.1 and r1 < r2 * 0.8:
            is_squat = True

    state_str = "🟦" if is_squat else ""

    return pat_str, direction, state_str

async def run_scan(message: Message, interval: str = "all"):
    now_str = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)).strftime("%d.%m.%2y %H:%M")
    await message.answer(f"🔍 Запускаю автоотчет ({now_str} МСК)...")

    timeframes = ["1h", "4h", "1d"] if interval == "all" else [interval]
    rows = []

    for sym in SCAN_SYMBOLS:
        clean_name = sym.replace("-USDT", "").replace("SILVER", "XAG").replace("PAXG", "XAU")[:3]
        
        for tf in timeframes:
            try:
                klines = await fetch_bingx_candles(sym, timeframe=tf, limit=30, interval=tf)
                if not klines or len(klines) < 22:
                    continue

                df = pd.DataFrame(klines)
                last_closed = df.iloc[-2]
                
                # Время закрытия
                ts = float(last_closed.get("time", last_closed.get("timestamp", 0)))
                dt = datetime.datetime.fromtimestamp(ts / 1000, tz=datetime.timezone.utc) + datetime.timedelta(hours=3)
                time_str = dt.strftime("%H:%M")

                pat, dir_icon, state_icon = analyze_bar_patterns(df)

                # Добавляем в список только при наличии паттерна или сквота (для чистоты) или для общих ТФ
                rows.append({
                    "act": clean_name,
                    "time": time_str,
                    "tf": tf,
                    "dir": dir_icon,
                    "pat": pat,
                    "state": state_icon
                })
            except Exception as e:
                logging.error(f"Ошибка автоотчета {sym} {tf}: {e}")

    if not rows:
        await message.answer("⚠️ Не удалось сформировать отчет.")
        return

    table_text = f"📊 <b>Автоотчет на {now_str} МСК:</b>\n\n<pre>"
    table_text += f"{'АКТ':<4} | {'ВРЕМЯ':<5} | {'ТФ':<3} | {'НАПР'} | {'ПАТ':<7} | {'СОСТ'}\n"
    table_text += "-" * 38 + "\n"

    for r in rows:
        table_text += f"{r['act']:<4} | {r['time']:<5} | {r['tf']:<3} |  {r['dir']}   | {r['pat']:<7} | {r['state']}\n"

    table_text += "</pre>"
    await message.answer(table_text)

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
async def cmd_scan_all(message: Message): await run_scan(message, "all")

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
    delete_alert(alert_id)
    await callback.answer("Алерт удален!")
    
    text, buttons = format_alerts_table(chat_id=callback.message.chat.id)
    keyboard = build_compact_keyboard(buttons, row_width=4) if buttons else None
    
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        pass

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
