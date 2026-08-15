import datetime
import logging
import pandas as pd
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, ContentType

from core.fetcher import fetch_klines, SCAN_SYMBOLS
from core.patterns import analyze_patterns
from core.formatter import format_table_report, format_alerts_table, build_compact_keyboard
from core.database import clear_all_alerts, delete_alert
from core.stt import transcribe_voice

router = Router()

HELP_TEXT = """
📖 <b>Справка по использованию бота BingX Price Action</b>

<b>Основные команды:</b>
• /scan — Полное сканирование всех ТФ (1H, 4H, 1D)
• /scan [дата время] — Исторический срез (например: <code>/scan 10.08 19:00</code>)
• /scan_1h, /scan_4h, /scan_1d — Сканирование конкретного ТФ
• /del_all — Очистка всех созданных алертов
• /help — Вызов данного справочного меню

------------------------------------
<b>Сокращения паттернов (колонка ПАТ):</b>
• <b>Pin</b> — Пин-бар (Pin Bar)
• <b>Out</b> — Внешний бар / Поглощение (Outside Bar)
• <b>Ins</b> — Внутренний бар (Inside Bar)
• <b>PPR</b> — Разворотной паттерн (Pivot Point Reversal)
• <b>Fak</b> — Фейки / Ложный пробой (Fakey)
*(Если на свече несколько паттернов, они пишутся через слэш, напр: <code>Fak/Pin</code>)*

------------------------------------
<b>Значения эмодзи:</b>
• 🟡 / 🔴 — Направление бара (Бычий / Медвежий)
• 🔹 — Приседающий бар по Биллу Вильямсу (Squat)
• ☀️ — Сжатие волатильности (Ленты Боллинджера внутри Кельтнера)
• 💥 — Взрыв / Расширение волатильности
"""

def parse_historical_datetime(args_str: str) -> datetime.datetime:
    if not args_str or not args_str.strip():
        return None
    
    clean_str = args_str.strip()
    now_msk = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)
    
    formats = [
        ("%d %H:%M", "day"),
        ("%d.%m %H:%M", "day_month"),
        ("%d.%m.%y %H:%M", "full_short"),
        ("%d.%m.%Y %H:%M", "full_long"),
    ]
    
    for fmt, mode in formats:
        try:
            dt = datetime.datetime.strptime(clean_str, fmt)
            if mode == "day":
                dt = dt.replace(year=now_msk.year, month=now_msk.month)
            elif mode == "day_month":
                dt = dt.replace(year=now_msk.year)
            
            msk_tz = datetime.timezone(datetime.timedelta(hours=3))
            return dt.replace(tzinfo=msk_tz)
        except ValueError:
            continue
            
    return None

async def run_scan(message: Message, interval: str = "all", is_auto: bool = False, target_dt: datetime.datetime = None):
    now_dt = target_dt if target_dt else (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3))
    now_str = now_dt.strftime("%d.%m.%y %H:%M")
    
    tf_title = "Все ТФ" if interval == "all" else interval
    if target_dt:
        title_name = f"Сканирование {tf_title} ({now_str} МСК)"
        status_text = f"🔍 Сканирую историю на {now_str} МСК ({tf_title})..."
    elif is_auto:
        title_name = f"АвтоОтчёт ({now_str} МСК)"
        status_text = f"🔍 Запускаю автоотчет ({now_str} МСК)..."
    else:
        title_name = f"Сканирование {tf_title} ({now_str} МСК)"
        status_text = f"🔍 Запускаю сканирование {tf_title}..."

    status_msg = await message.answer(status_text)

    timeframes = ["1h", "4h", "1d"] if interval == "all" else [interval]
    all_signals = []

    fetch_limit = 1000 if target_dt else 30
    target_ts_ms = int(target_dt.timestamp() * 1000) if target_dt else None

    for sym in SCAN_SYMBOLS:
        for tf in timeframes:
            try:
                klines = await fetch_klines(sym, interval=tf, limit=fetch_limit)
                if not klines or len(klines) < 3:
                    continue

                df = pd.DataFrame(klines)
                df['time'] = pd.to_numeric(df['time'], errors='coerce')
                df.loc[df['time'] < 10000000000, 'time'] *= 1000

                if target_ts_ms:
                    df = df[df['time'] <= target_ts_ms]

                if len(df) < 3:
                    continue

                pats = analyze_patterns(df)
                curr = df.iloc[-1]
                bar_time = int(curr.get('time'))
                direction = "bull" if curr['close'] >= curr['open'] else "bear"

                for p in pats:
                    all_signals.append({
                        "symbol": sym,
                        "tf": tf,
                        "pattern": p,
                        "direction": direction,
                        "bar_time": bar_time,
                        "is_forming": False
                    })

            except Exception as e:
                logging.error(f"Ошибка при сканировании {sym} ({tf}): {e}")

    report_text = format_table_report(all_signals, report_title=title_name, now_dt=now_dt, tf_type=interval)
    
    await status_msg.delete()
    if all_signals:
        await message.answer(report_text, parse_mode="HTML")
    else:
        await message.answer(f"📊 <b>{title_name}</b>\nПаттерны не обнаружены.")

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT, parse_mode="HTML")

@router.message(Command("scan"))
async def cmd_scan_all(message: Message, command: CommandObject):
    target_dt = parse_historical_datetime(command.args)
    await run_scan(message, "all", is_auto=False, target_dt=target_dt)

@router.message(Command("scan_1h"))
async def cmd_scan_1h(message: Message, command: CommandObject):
    target_dt = parse_historical_datetime(command.args)
    await run_scan(message, "1h", is_auto=False, target_dt=target_dt)

@router.message(Command("scan_4h"))
async def cmd_scan_4h(message: Message, command: CommandObject):
    target_dt = parse_historical_datetime(command.args)
    await run_scan(message, "4h", is_auto=False, target_dt=target_dt)

@router.message(Command("scan_1d"))
async def cmd_scan_1d(message: Message, command: CommandObject):
    target_dt = parse_historical_datetime(command.args)
    await run_scan(message, "1d", is_auto=False, target_dt=target_dt)

@router.message(Command("scan_1w"))
async def cmd_scan_1w(message: Message, command: CommandObject):
    target_dt = parse_historical_datetime(command.args)
    await run_scan(message, "1w", is_auto=False, target_dt=target_dt)

@router.message(Command("del_all"))
async def cmd_del_all(message: Message):
    clear_all_alerts(message.chat.id)
    await message.answer("🗑 Все активные алерты успешно удалены!")

@router.callback_query(F.data.startswith("del_alert_"))
async def process_del_alert(callback: CallbackQuery):
    alert_id = int(callback.data.split("_")[2])
    delete_alert(alert_id, callback.message.chat.id)
    await callback.answer("Алерт удален!")
    
    text, buttons = format_alerts_table(chat_id=callback.message.chat.id)
    keyboard = build_compact_keyboard(buttons, row_width=4) if buttons else None
    
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
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
            
        await status_msg.edit_text(f"🗣 <i>«{text}»</i>")
    except Exception as e:
        logging.error(f"Ошибка распознавания голоса: {e}")
        await status_msg.edit_text("❌ Произошла ошибка при распознавании речи.")

def register_custom_handlers(dp, bot=None):
    """Регистрация роутера хэндлеров в aiogram Dispatcher."""
    if 'router' in globals():
        dp.include_router(router)

from core.ai_handler import clean_symbol
