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
