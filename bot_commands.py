import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SYMBOL_MAP, TIMEFRAMES
from scheduler import scan_and_notify

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    msg = (
        "🤖 **BingX Price Action Bot v0.4**\n\n"
        "Доступные команды:\n"
        "▫️ `/scan` — Запустить немедленный скан рынка\n"
        "▫️ `/list` — Список отслеживаемых активов\n"
        "▫️ `/status` — Статус работы бота\n"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /list"""
    assets_str = ", ".join(SYMBOL_MAP.keys())
    tf_str = ", ".join(TIMEFRAMES)
    msg = (
        f"📊 **Отслеживаемые активы ({len(SYMBOL_MAP)}):**\n`{assets_str}`\n\n"
        f"⏱ **Таймфреймы:** `{tf_str}`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status"""
    msg = "🟢 **Бот работает штатно.**\nАвтосканирование выполняется каждый час в `XX:55` MSK."
    await update.message.reply_text(msg, parse_mode="Markdown")

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /scan — ручной запуск"""
    await update.message.reply_text("🔎 **Запускаю ручное сканирование рынка...**", parse_mode="Markdown")
    # Запускаем функцию сканирования
    await scan_and_notify()
    await update.message.reply_text("✅ Сканирование завершено.", parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help — информация о командах и эмодзи."""
    help_text = (
        "📚 **Справка по командам и обозначениям:**\n\n"
        "**Общие команды:**\n"
        "▫️ `/start` — Приветствие и краткий список команд.\n"
        "▫️ `/help` — Эта справка.\n"
        "▫️ `/list` — Показать все отслеживаемые активы и таймфреймы.\n"
        "▫️ `/status` — Проверить статус работы бота.\n\n"
        "**Сканирование рынка:**\n"
        "▫️ `/scan` — Ручное сканирование всех ТФ. \n"
        "   Например: `/scan` (сейчас) или `/scan 15.08 10:00` (исторический скан).\n"
        "▫️ `/scan_1h`, `/scan_4h`, `/scan_1d`, `/scan_1w` — Ручное сканирование конкретного ТФ.\n\n"
        "**Управление алертами:**\n"
        "▫️ `/alerts` — Показать все ваши активные алерты.\n"
        "▫️ `/del_all` — Удалить ВСЕ ваши активные алерты.\n"
        "▫️ **Создание алерта голосом или текстом:**\n"
        "   Например: _«Поставь алерт на KAS на 0.1249»_\n"
        "   Или: _«Когда Эфир пробьет хай вчерашней дневной свечи?»_\n"
        "   Или: _«Алерт на ADA по лоу 4-часовой свечи закрытой в 10:00»_\n\n"
        "**Эмодзи в отчётах:**\n"
        "▫️ `🟡🟡🟡` — Направление тренда по BB: сильное восходящее.\n"
        "▫️ `🔴🔴🔴` — Направление тренда по BB: сильное нисходящее.\n"
        "▫️ `⚪⚪⚪` — Направление тренда по BB: флэт или смешанное.\n"
        "▫️ `☀️` — Состояние свечи: `Squeeze` (сужение волатильности).\n"
        "▫️ `💥` — Состояние свечи: `Expansion` (расширение волатильности).\n"
        "▫️ `🔷` — Состояние свечи: `Squat` (узкое тело при потенциально большом объеме - текущая заглушка без анализа объема).\n"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")
