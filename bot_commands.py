from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeDefault

async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="scan", description="Сканировать все ТФ"),
        BotCommand(command="scan_1h", description="Сканировать 1H"),
        BotCommand(command="scan_4h", description="Сканировать 4H"),
        BotCommand(command="scan_1d", description="Сканировать 1D"),
        BotCommand(command="del_all", description="Удалить все алерты"),
        BotCommand(command="help", description="Справка и расшифровка обозначений"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
