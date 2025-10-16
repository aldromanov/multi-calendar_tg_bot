import asyncio

from database import init_db
from config import logger, CALENDAR_TOKENS
from multicalendar import MultiCalendarManager
from telegram_bot import TelegramBot


def main():
    logger.info("Запуск бота...")
    init_db()

    cal_manager = MultiCalendarManager(CALENDAR_TOKENS)
    bot = TelegramBot()
    bot.set_calendar_client(cal_manager)
    logger.info("Запуск Telegram бота...")
    loop = asyncio.get_event_loop()

    try:
        loop.create_task(bot.start_scheduler_task())
        logger.info("Запущен планировщик задач Telegram бота")
        loop.create_task(bot.set_bot_commands())
        logger.info("Установлены команды Telegram бота")
        bot.app.run_polling()
    finally:
        loop.close()
        logger.info("Бот завершил работу.")


if __name__ == "__main__":
    main()
