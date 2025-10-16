import datetime as dt

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

from config import (
    TELEGRAM_TOKEN,
    CALENDAR_TOKENS,
    TZINFO,
    logger,
    NOTIFY_CHAT_ID,
    CHECK_INTERVAL,
    AHEAD_MINUTES,
)
from database import SessionLocal, SeenEvent
from notifier_worker import NotifierWorker
from utils import format_event, get_user_id


def format_confirmed_message(original_text: str) -> str:
    """
    Возвращает отформатированный текст подтверждённого события.
    """
    parts = original_text.split("\n", 2)
    if len(parts) < 3:
        return f"🎯 <b>Событие подтверждено</b>\n<code>{original_text}</code>"

    header = (
        parts[0]
        .replace("⏰ Скоро событие", "🎯 <b>Событие подтверждено</b>")
        .replace("⚡ Скоро событие", "🎯 <b>Событие подтверждено</b>")
    )
    return f"{header}\n<b>{parts[1]}</b>\n<code>{parts[2]}</code>"


class TelegramBot:
    """
    Telegram-бот для отображения событий календаря и отправки уведомлений.

    Поддерживает команды:
    - /today — события на сегодня
    - /tomorrow — события на завтра
    - /week — события на текущую неделю
    - /nextweek — события на следующую неделю

    Также интегрирован с NotifierWorker для автоматических уведомлений.
    """

    def __init__(self, token=TELEGRAM_TOKEN):
        """
        Инициализирует Telegram-бота и регистрирует обработчики команд.

        :param token: Токен Telegram-бота (по умолчанию из config.TELEGRAM_TOKEN)
        """
        self.token = token
        self.app = ApplicationBuilder().token(self.token).build()
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("today", self.today))
        self.app.add_handler(CommandHandler("tomorrow", self.tomorrow))
        self.app.add_handler(CommandHandler("week", self.week))
        self.app.add_handler(CommandHandler("nextweek", self.nextweek))
        self.app.add_handler(CallbackQueryHandler(self.confirm_event))

        self.cal_manager = None
        self.scheduler = None
        self.notifier = None
        logger.info("TelegramBot готов.")

    def set_calendar_client(self, client_manager) -> None:
        """
        Устанавливает менеджер календарей и настраивает планировщик уведомлений.

        :param client_manager: Экземпляр менеджера клиентов календарей.
        """
        self.cal_manager = client_manager
        self.scheduler = AsyncIOScheduler()
        self.notifier = NotifierWorker(client_manager, self.app, NOTIFY_CHAT_ID, self.scheduler)
        self.scheduler.add_job(self.notifier.check_and_notify, "interval", seconds=CHECK_INTERVAL)

        async def start_scheduler():
            self.scheduler.start()
            logger.info(
                f"Scheduler уведомлений запущен (интервал {CHECK_INTERVAL} сек., оповещение за {AHEAD_MINUTES} мин.)"
            )

        self.start_scheduler_task = start_scheduler

    async def set_bot_commands(self) -> None:
        """
        Устанавливает список команд для Telegram-бота.
        """
        commands = [
            BotCommand("today", "События на сегодня"),
            BotCommand("tomorrow", "События на завтра"),
            BotCommand("week", "События на эту неделю"),
            BotCommand("nextweek", "События на следующую неделю"),
        ]
        await self.app.bot.set_my_commands(commands)
        logger.info("Команды бота установлены.")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Обрабатывает команду /start.
        Отправляет приветственное сообщение и список подключённых календарей.
        """
        calendars_list = []
        for cfg in CALENDAR_TOKENS.values():
            names = ", ".join(cfg["calendars"].keys())
            calendars_list.append(f"👤 {names}")

        calendars_text = "\n".join(calendars_list)

        text = (
            "👋 <b>Привет!</b>\n\n"
            "📅 Я бот, который отслеживает события Google Calendar.\n\n"
            f"Подключённые календари:\n<b>{calendars_text}</b>\n\n"
            "Список команд:\n"
            "➡️ <b>/today</b> - события на <i>сегодня</i>\n"
            "➡️ <b>/tomorrow</b> - события на <i>завтра</i>\n"
            "➡️ <b>/week</b> - события на <i>текущую неделю</i>\n"
            "➡️ <b>/nextweek</b> - события на <i>следующую неделю</i>\n\n"
            "⏰ Также отправляю уведомления о предстоящих событиях \n"
        )

        if not update.message:
            return

        await update.message.reply_text(
            text,
            parse_mode="HTML",
            disable_web_page_preview=False,
        )
        logger.info(f"Команда /start от {get_user_id(update.effective_user)}")

    async def confirm_event(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Обрабатывает подтверждение события пользователем (callback query).
        Обновляет запись в базе данных и изменяет сообщение в чате.
        """
        query = update.callback_query

        if not (query and query.message):
            return

        await query.answer()
        ev_hash = query.data

        try:
            with SessionLocal() as session:
                updated = (
                    session.query(SeenEvent)
                    .filter_by(event_id=ev_hash)
                    .update({"confirmed": True}, synchronize_session=False)
                )
                session.commit()

            if updated:
                logger.info(f"Событие {ev_hash} подтверждено пользователем {get_user_id(update.effective_user)}")
            else:
                logger.warning(f"Событие {ev_hash} не найдено для подтверждения")
        except Exception as e:
            logger.error(f"Ошибка при подтверждении события {ev_hash}: {e}", exc_info=True)
            await query.answer("Ошибка при подтверждении события.")
            return

        await query.answer("Событие подтверждено ✅")
        await query.edit_message_reply_markup(reply_markup=None)

        new_text = format_confirmed_message(query.message.text or "")
        await query.edit_message_text(
            new_text,
            parse_mode="HTML",
            disable_web_page_preview=False,
        )

    async def today(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Команда /today — показывает события на сегодня."""
        await self._show_day(update, 0, "сегодня")

    async def tomorrow(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Команда /tomorrow — показывает события на завтра."""
        await self._show_day(update, 1, "завтра")

    async def week(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Команда /week — показывает события на текущую неделю."""
        await self._show_week(update, 0, "на эту неделю")

    async def nextweek(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Команда /nextweek — показывает события на следующую неделю."""
        await self._show_week(update, 1, "на следующую неделю")

    async def _show_week(self, update: Update, week_offset: int, label: str) -> None:
        """
        Отправляет список событий на указанную неделю.

        :param week_offset: 0 — текущая неделя, 1 — следующая.
        :param label: Текстовое обозначение периода (для сообщения).
        """
        if await self._cal_manager_error(update):
            return
        now_local = dt.datetime.now(TZINFO).date()
        offset = dt.timedelta(weeks=week_offset)
        start_of_week = now_local - dt.timedelta(days=now_local.weekday())
        day = start_of_week + offset
        events_dict = self._collect_events_for_period(day, "week")
        await self._send_events_list(update, label, events_dict)

    async def _show_day(self, update: Update, days_offset: int, label: str) -> None:
        """
        Отправляет список событий на конкретный день.

        :param days_offset: Смещение от текущего дня (0 — сегодня, 1 — завтра).
        :param label: Текстовое обозначение периода (для сообщения).
        """
        if await self._cal_manager_error(update):
            return
        offset = dt.timedelta(days=days_offset)
        day = dt.datetime.now(TZINFO).date() + offset
        events_dict = self._collect_events_for_period(day, "day")
        await self._send_events_list(update, label, events_dict)

    async def _cal_manager_error(self, update: Update) -> bool:
        """
        Проверяет, инициализирован ли клиент календаря.

        :return: True, если клиент не инициализирован (сообщение отправлено пользователю).
        """
        if not self.cal_manager:
            if update.message:
                await update.message.reply_text(
                    "Календарный клиент не инициализирован.",
                )
                return True
        return False

    def _collect_events_for_period(self, date: dt.date, period: str) -> dict[str, list[dict]]:
        """
        Собирает события для всех пользователей на указанный день или неделю.

        :param date: Дата (для дня) или первый день недели.
        :param period: "day" или "week".
        :return: Словарь вида {calendar_name: [events]}.
        """
        events_dict = {}
        for user, cfg in CALENDAR_TOKENS.items():
            client = self.cal_manager.clients[user]["client"]
            for name, cid in cfg["calendars"].items():
                if period == "day":
                    evs = client.get_events_for_day(cid, date)
                else:
                    evs = client.get_events_for_week(cid, date)
                events_dict[name] = evs
        return events_dict

    async def _send_events_list(self, update: Update, label: str, events_dict: dict[str, list[dict]]) -> None:
        """
        Формирует и отправляет список событий пользователю.

        :param label: Подпись периода ("сегодня", "на неделю" и т. д.)
        :param events_dict: Словарь событий по календарям.
        """
        out: list[str] = []
        header = f"📅 <b>События {label}</b>\n"
        for name, evs in events_dict.items():
            if evs:
                out.append(f"\n<b>{name}</b>")
                out += [format_event(e) for e in evs]

        if out:
            await update.message.reply_text(
                header + "\n".join(out),
                parse_mode="HTML",
                disable_web_page_preview=False,
            )
            logger.info(f"Отправлен список событий {label} пользователю {get_user_id(update.effective_user)}")
        else:
            await update.message.reply_text(f"Нет событий {label}.")
