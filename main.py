import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import TELEGRAM_BOT_TOKEN
from core.database import init_db
from core.ai_handler import timer_checker_loop
from core.handlers import register_custom_handlers

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

async def main():
    # Инициализация БД
    init_db()
    
    # Регистрация всех команд (/scan, /scan_15m, /alerts, /del_all, голос и AI)
    register_custom_handlers(dp, bot)
    
    # Запуск фонового проверяльщика таймеров
    asyncio.create_task(timer_checker_loop(bot))
    
    logging.info("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
