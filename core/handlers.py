import os
import asyncio
from datetime import datetime, timezone, timedelta
from aiogram import F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from core.ai_handler import process_ai_message, format_alerts_table
from core.formatter import format_table_report
from core.database import get_all_alerts, delete_alert, clear_all_alerts
from core.fetcher import fetch_klines
from core.patterns import analyze_patterns
from groq import Groq

MSK_TZ = timezone(timedelta(hours=3))
TF_PRIORITY = {"1w": 4, "1d": 3, "4h": 2, "1h": 1, "15m": 0}

def clean_symbol(symbol: str) -> str:
    return symbol.replace("-USDT", "").replace("USDT", "")

def build_inline_keyboard(raw_buttons):
    if not raw_buttons: return None
    kb = []
    for row in raw_buttons:
        kb_row = [InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"]) for btn in row]
        kb.append(kb_row)
    return InlineKeyboardMarkup(inline_keyboard=kb)

def register_custom_handlers(dp, bot=None):
    
    # Полный список активов (включая Золото XAU и Серебро XAG)
    COINS = [
        "BTC-USDT", "ETH-USDT", "SOL-USDT", "KAS-USDT", "LTC-USDT", 
        "DOT-USDT", "DOGE-USDT", "ATOM-USDT", "ADA-USDT",
        "XAU-USDT", "XAG-USDT"
    ]

    # --- СКАНИРОВАНИЕ ОТДЕЛЬНОГО ТФ ---
    async def run_scan(message: Message, tf: str):
        status_msg = await message.answer(f"⏳ Сканирую {tf}...")
        try:
            report_data = []
            for coin in COINS:
                df = await fetch_klines(coin, tf, limit=30)
                if df is not None:
                    pats = analyze_patterns(df)
                    if pats:
                        # В зависимости от логики правила 5 минут берем iloc[-1] или iloc[-2]
                        now_dt = datetime.now(MSK_TZ)
                        curr = df.iloc[-1] if now_dt.minute >= 55 else df.iloc[-2]
                        direction = "bull" if curr['close'] >= curr['open'] else "bear"
                        for p in pats:
                            report_data.append({"symbol": clean_symbol(coin), "tf": tf, "pattern": p, "direction": direction})
            
            if report_data:
                await message.answer(format_table_report(report_data, report_title=f"Отчёт {tf}", now_dt=datetime.now(MSK_TZ), tf_type=tf), parse_mode="HTML")
            else:
                await message.answer(f"✅ На {tf} интересных паттернов пока не найдено.")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}")
        finally:
            try:
                await status_msg.delete()
            except TelegramBadRequest:
                pass

    # --- СВОДНОЕ СКАНИРОВАНИЕ ВСЕХ ТФ ДЛЯ КОМАНДЫ /scan ---
    @dp.message(Command("scan"))
    async def cmd_scan_all(message: Message):
        status_msg = await message.answer("⏳ Сканирую все таймфреймы (1W, 1D, 4H, 1H)...")
        try:
            timeframes = ["1w", "1d", "4h", "1h"]
            all_signals = []
            
            for tf in timeframes:
                for coin in COINS:
                    df = await fetch_klines(coin, tf, limit=30)
                    if df is not None:
                        pats = analyze_patterns(df)
                        if pats:
                            now_dt = datetime.now(MSK_TZ)
                            curr = df.iloc[-1] if now_dt.minute >= 55 else df.iloc[-2]
                            direction = "bull" if curr['close'] >= curr['open'] else "bear"
                            for p in pats:
                                all_signals.append({
                                    "symbol": clean_symbol(coin),
                                    "tf": tf,
                                    "pattern": p,
                                    "direction": direction
                                })
            
            # Сортировка: 1. Алфавит активов (A-Z), 2. Старшинство ТФ (1W -> 1D -> 4H -> 1H)
            all_signals.sort(key=lambda x: (x["symbol"], -TF_PRIORITY.get(x["tf"].lower(), 0)))
            
            now_dt = datetime.now(MSK_TZ)
            title = f"📊 Сводный Отчёт ({now_dt.strftime('%d.%m.%Y %H:%M MSK')})"
            
            if all_signals:
                report_text = format_table_report(all_signals, report_title=title, now_dt=now_dt, tf_type="multi")
                await message.answer(report_text, parse_mode="HTML")
            else:
                await message.answer(f"<b>{title}</b>\n\n✅ Сигналов по отслеживаемым паттернам не найдено.", parse_mode="HTML")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}")
        finally:
            try:
                await status_msg.delete()
            except TelegramBadRequest:
                pass

    @dp.message(Command("scan_1h"))
    async def cmd_scan_1h(message: Message): await run_scan(message, "1h")
    @dp.message(Command("scan_4h"))
    async def cmd_scan_4h(message: Message): await run_scan(message, "4h")
    @dp.message(Command("scan_1d"))
    async def cmd_scan_1d(message: Message): await run_scan(message, "1d")
    @dp.message(Command("scan_1w"))
    async def cmd_scan_1w(message: Message): await run_scan(message, "1w")

    # --- 15М СКАНИРОВАНИЕ ---
    @dp.message(Command("scan_15m"))
    async def cmd_scan_15m_menu(message: Message):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="BTC", callback_data="track15m_BTC-USDT"), InlineKeyboardButton(text="ETH", callback_data="track15m_ETH-USDT"), InlineKeyboardButton(text="SOL", callback_data="track15m_SOL-USDT")],
            [InlineKeyboardButton(text="KAS", callback_data="track15m_KAS-USDT"), InlineKeyboardButton(text="LTC", callback_data="track15m_LTC-USDT"), InlineKeyboardButton(text="DOT", callback_data="track15m_DOT-USDT")],
            [InlineKeyboardButton(text="DOGE", callback_data="track15m_DOGE-USDT"), InlineKeyboardButton(text="ATOM", callback_data="track15m_ATOM-USDT"), InlineKeyboardButton(text="ADA", callback_data="track15m_ADA-USDT")]
        ])
        await message.answer("🎯 <b>Выберите актив для слежения 15М (4 свечи за 2 мин до закрытия):</b>", reply_markup=keyboard, parse_mode="HTML")

    @dp.callback_query(F.data.startswith("track15m_"))
    async def process_15m_tracking(callback: CallbackQuery):
        symbol_full = callback.data.replace("track15m_", "")
        symbol_short = clean_symbol(symbol_full)
        await callback.answer(f"Включено слежение за {symbol_short}!")
        await callback.message.edit_text(f"🎯 <b>Запущено слежение 15M для {symbol_short}</b>\n\n⏱ Бот пришлёт отчёт 4 раза: в :13, :28, :43 и :58 минут.", parse_mode="HTML")
        asyncio.create_task(_run_15m_tracker(callback.message.bot, callback.message.chat.id, symbol_full))

    async def _run_15m_tracker(bot_inst, chat_id: int, symbol_full: str):
        symbol_short = clean_symbol(symbol_full)
        for check_num in range(1, 5):
            now = datetime.now(MSK_TZ)
            target_minutes = [13, 28, 43, 58]
            future_times = []
            for m in target_minutes:
                dt = now.replace(minute=m, second=0, microsecond=0)
                if dt <= now:
                    dt += timedelta(hours=1) if m == 13 and now.minute >= 58 else timedelta(minutes=0)
                    if dt <= now: continue
                future_times.append(dt)
            next_target = min(future_times) if future_times else (now + timedelta(hours=1)).replace(minute=13, second=0, microsecond=0)
            await asyncio.sleep((next_target - now).total_seconds())
            try:
                df = await fetch_klines(symbol_full, "15m", limit=30)
                if df is not None:
                    pats = analyze_patterns(df)
                    curr = df.iloc[-1]
                    sig = [{"symbol": symbol_short, "tf": "15m", "pattern": p if pats else "Формирование", "direction": "bull" if curr['close'] >= curr['open'] else "bear", "is_forming": True} for p in (pats or ["15M Бар"])]
                    await bot_inst.send_message(chat_id=chat_id, text=format_table_report(sig, report_title=f"15M Отчёт [{check_num}/4] {symbol_short}", now_dt=datetime.now(MSK_TZ), tf_type="15m"), parse_mode="HTML")
            except Exception: pass

    # --- АЛЕРТЫ ПО КОМАНДЕ /alerts ---
    @dp.message(Command("alerts"))
    async def cmd_alerts(message: Message):
        table_text, raw_buttons = format_alerts_table(chat_id=message.chat.id)
        reply_markup = build_inline_keyboard(raw_buttons)
        await message.answer(table_text, parse_mode="HTML", reply_markup=reply_markup)

    @dp.callback_query(F.data.startswith("del_alert_"))
    async def process_del_alert_callback(callback: CallbackQuery):
        alert_id = int(callback.data.replace("del_alert_", ""))
        delete_alert(alert_id=alert_id, chat_id=callback.message.chat.id)
        await callback.answer("Алерт удалён!")
        
        table_text, raw_buttons = format_alerts_table(chat_id=callback.message.chat.id)
        reply_markup = build_inline_keyboard(raw_buttons)
        try:
            await callback.message.edit_text(table_text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception:
            await callback.message.answer(table_text, parse_mode="HTML", reply_markup=reply_markup)

    @dp.message(Command("del_all"))
    async def cmd_del_all(message: Message):
        clear_all_alerts(chat_id=message.chat.id)
        await message.answer("🗑 <b>Все алерты удалены!</b>", parse_mode="HTML")

    # --- ГОЛОС ---
    @dp.message(F.voice)
    async def handle_voice_message(message: Message):
        status_msg = await message.answer("🎙 <i>Распознаю голос...</i>", parse_mode="HTML")
        ogg_path = f"/tmp/voice_{message.message_id}.ogg"
        mp3_path = f"/tmp/voice_{message.message_id}.mp3"
        try:
            file_info = await message.bot.get_file(message.voice.file_id)
            await message.bot.download_file(file_info.file_path, ogg_path)
            os.system(f"ffmpeg -y -i {ogg_path} -acodec libmp3lame {mp3_path} >/dev/null 2>&1")
            
            groq_key = os.getenv("GROQ_API_KEY")
            client = Groq(api_key=groq_key)
            with open(mp3_path, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    file=(mp3_path, audio_file.read()),
                    model="whisper-large-v3-turbo",
                    language="ru"
                )
            
            user_text = transcription.text.strip()
            await status_msg.edit_text(f"🗣 <b>Вы сказали:</b> «{user_text}»", parse_mode="HTML")
            
            res = await process_ai_message(user_text, chat_id=message.chat.id)
            if res and "content" in res:
                reply_markup = build_inline_keyboard(res.get("markup"))
                await message.answer(res["content"], parse_mode="HTML", reply_markup=reply_markup)
                
        except Exception as e:
            await status_msg.edit_text(f"❌ Ошибка: {e}")
        finally:
            if os.path.exists(ogg_path): os.remove(ogg_path)
            if os.path.exists(mp3_path): os.remove(mp3_path)

    # --- ТЕКСТ ---
    @dp.message(~F.text.startswith("/"))
    async def handle_ai_message(message: Message):
        res = await process_ai_message(message.text, chat_id=message.chat.id)
        if res and "content" in res:
            reply_markup = build_inline_keyboard(res.get("markup"))
            await message.answer(res["content"], parse_mode="HTML", reply_markup=reply_markup)
