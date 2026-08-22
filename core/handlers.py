import logging
from datetime import datetime, timezone, timedelta
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

from core.bingx.candles import fetch_bingx_candles
from core.patterns import analyze_patterns
from core.formatter import format_report, clean_symbol, MSK_TZ

router = Router()

SYMBOLS = [
    "BTC-USDT", "ETH-USDT", "SOL-USDT", "LTC-USDT", 
    "ADA-USDT", "DOT-USDT", "ATOM-USDT", "XRP-USDT", 
    "DOGE-USDT", "KAS-USDT"
]

def register_custom_handlers(dp, bot=None):
    dp.include_router(router)

async def run_scan(message: Message, tf: str):
    now_msk = datetime.now(MSK_TZ)
    status_msg = await message.answer(f"🔍 Сканирую рынок ({tf})...")
    
    all_signals = []
    
    for sym_full in SYMBOLS:
        try:
            # Запрашиваем 600 свечей для точного расчета BB(480)
            klines = await fetch_bingx_candles(sym_full, tf=tf, limit=600)
            if klines is None or klines.empty or len(klines) < 30:
                continue

            candles_list = klines.to_dict('records')
            pat_data = analyze_patterns(candles_list)
            
            if pat_data and pat_data.get("pattern") and pat_data["pattern"] != "-": 
                last_closed_candle = klines.iloc[-1]
                
                all_signals.append({
                    "symbol": clean_symbol(sym_full),
                    "tf": tf,
                    "pattern": pat_data["pattern"],
                    "direction_bb": pat_data.get("direction_bb", '⚪⚪⚪'),
                    "state_emoji": pat_data.get("state_emoji", ''),
                    "bb_breakthrough": pat_data.get("bb_breakthrough", ''),
                    "is_auto": False,
                    "timestamp": last_closed_candle['timestamp']
                })
        except Exception as e:
            logging.error(f"Ошибка сканирования {sym_full} {tf}: {e}")

    report_text = format_report(all_signals, is_auto=False, now_dt=now_msk)
    await status_msg.edit_text(report_text, parse_mode="HTML")

@router.message(Command("scan_1h"))
async def cmd_scan_1h(message: Message):
    await run_scan(message, "1h")

@router.message(Command("scan_4h"))
async def cmd_scan_4h(message: Message):
    await run_scan(message, "4h")

@router.message(Command("scan_1d"))
async def cmd_scan_1d(message: Message):
    await run_scan(message, "1d")

@router.message(Command("scan_1w"))
async def cmd_scan_1w(message: Message):
    await run_scan(message, "1w")

@router.message(Command("scan"))
async def cmd_scan_all(message: Message):
    now_msk = datetime.now(MSK_TZ)
    status_msg = await message.answer("🔍 Запуск полного сканирования (1w, 1d, 4h, 1h)...")
    
    all_signals = []
    tfs = ["1w", "1d", "4h", "1h"]
    
    for tf in tfs:
        for sym_full in SYMBOLS:
            try:
                klines = await fetch_bingx_candles(sym_full, tf=tf, limit=600)
                if klines is None or klines.empty or len(klines) < 30:
                    continue

                candles_list = klines.to_dict('records')
                pat_data = analyze_patterns(candles_list)
                
                if pat_data and pat_data.get("pattern") and pat_data["pattern"] != "-": 
                    last_closed_candle = klines.iloc[-1]
                    
                    all_signals.append({
                        "symbol": clean_symbol(sym_full),
                        "tf": tf,
                        "pattern": pat_data["pattern"],
                        "direction_bb": pat_data.get("direction_bb", '⚪⚪⚪'),
                        "state_emoji": pat_data.get("state_emoji", ''),
                        "bb_breakthrough": pat_data.get("bb_breakthrough", ''),
                        "is_auto": False,
                        "timestamp": last_closed_candle['timestamp']
                    })
            except Exception as e:
                logging.error(f"Ошибка мультискана {sym_full} {tf}: {e}")

    report_text = format_report(all_signals, is_auto=False, now_dt=now_msk)
    await status_msg.edit_text(report_text, parse_mode="HTML")
