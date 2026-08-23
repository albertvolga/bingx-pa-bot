import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from core.bingx.candles import fetch_bingx_candles
from core.patterns import analyze_patterns
from core.formatter import format_report, clean_symbol, MSK_TZ
from core.database import get_all_alerts, clear_all_alerts, delete_alert, set_alert_recurring
from core.ai_intent import process_ai_command, format_alerts_list
from config import SYMBOL_MAP

logger = logging.getLogger(__name__)
router = Router()
SYMBOLS = [f"{s}-USDT" for s in SYMBOL_MAP.keys()]

def register_custom_handlers(dp, bot=None):
    dp.include_router(router)

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("👋 <b>Бот активен!</b>\n\nИспользуйте меню или пишите просто:\n<i>'поставь алерт на биткоин на 50000'</i>\n<i>'хай вчерашнего бара солана'</i>", parse_mode="HTML")

@router.message(Command("scan"))
async def cmd_scan(message: Message):
    status = await message.answer("🔍 Сканирую...")
    signals = []
    for tf in ["1w", "1d", "4h", "1h"]:
        for sym in SYMBOLS[:10]: # Быстрый скан топ-10
            try:
                klines = await fetch_bingx_candles(sym, tf=tf, limit=300)
                if klines is None or klines.empty: continue
                pat = analyze_patterns(klines.to_dict('records'))
                if pat and pat.get("pattern") != "-":
                    signals.append({"symbol": clean_symbol(sym), "tf": tf, "pattern": pat["pattern"], "direction_bb": pat.get("direction_bb", ''), "state_emoji": pat.get('state_emoji', ''), "is_auto": False, "timestamp": klines.iloc[-1]['time']})
            except: pass
    if signals:
        await status.edit_text(format_report(signals, is_auto=False), parse_mode="HTML")
    else:
        await status.edit_text("✅ Паттернов не найдено.")

@router.message(Command("scan_1h"))
async def cmd_scan_1h(m: Message): await run_single_scan(m, "1h")
@router.message(Command("scan_4h"))
async def cmd_scan_4h(m: Message): await run_single_scan(m, "4h")
@router.message(Command("scan_1d"))
async def cmd_scan_1d(m: Message): await run_single_scan(m, "1d")

async def run_single_scan(message: Message, tf: str):
    status = await message.answer(f"🔍 Скан {tf}...")
    signals = []
    for sym in SYMBOLS[:15]:
        try:
            klines = await fetch_bingx_candles(sym, tf=tf, limit=300)
            if klines is None or klines.empty: continue
            pat = analyze_patterns(klines.to_dict('records'))
            if pat and pat.get("pattern") != "-":
                signals.append({"symbol": clean_symbol(sym), "tf": tf, "pattern": pat["pattern"], "direction_bb": pat.get("direction_bb", ''), "state_emoji": pat.get('state_emoji', ''), "is_auto": False, "timestamp": klines.iloc[-1]['time']})
        except: pass
    txt = format_report(signals, is_auto=False) if signals else "✅ Чисто."
    await status.edit_text(txt, parse_mode="HTML")

@router.message(Command("alerts"))
async def cmd_alerts(message: Message):
    alerts = get_all_alerts(message.chat.id)
    kb = []
    text = format_alerts_list(alerts)
    for a in alerts:
        kb.append([InlineKeyboardButton(text=f"❌ {a['id']}", callback_data=f"del_{a['id']}")])
    kb.append([InlineKeyboardButton(text="🗑 ВСЕ", callback_data="del_all")])
    await message.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb) if kb else None)

@router.message(Command("del_all"))
async def cmd_del_all(message: Message):
    clear_all_alerts(message.chat.id)
    await message.answer("🗑 Все удалено.")

@router.message(Command("restart_bot"))
async def cmd_restart(message: Message):
    await message.answer("🔄 Перезагрузка... (секунду)")
    import os, signal
    os.kill(os.getpid(), signal.SIGTERM)

@router.callback_query(F.data.startswith("del_"))
async def cb_del(call):
    aid = int(call.data.split("_")[1])
    delete_alert(aid, chat_id=call.message.chat.id)
    await call.answer("Удалено")
    # Можно обновить сообщение, но пока просто ответ

@router.callback_query(F.data == "del_all")
async def cb_del_all(call):
    clear_all_alerts(call.message.chat.id)
    await call.answer("Все удалено")
    await call.message.edit_text("🗑 Все алерты удалены.")

@router.callback_query(F.data.startswith("set_recurring_"))
async def cb_rec(call):
    aid = int(call.data.split("_")[2])
    set_alert_recurring(aid, True)
    await call.answer("✅ Многоразовый")

@router.message()
async def handle_text(message: Message):
    if message.text.startswith("/"): return
    res = await process_ai_command(message.text, message.chat.id)
    if res["type"] != "ignore":
        await message.answer(res["message"], parse_mode="HTML")
