import datetime as dt

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from config import (
    BUTTON_TTL,
    CALENDAR_TOKENS,
    NOTIFY_CHAT_ID,
    NOTIFY_INTERVALS,
    TELEGRAM_TOKEN,
    TZINFO,
    logger,
)
from database import EventState, SeenEvent, SessionLocal
from notifier_worker import NotifierWorker
from utils import EventStatus, build_message, format_event, get_user_id


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

        self.app.add_handler(CallbackQueryHandler(self.notify_callback, pattern=r"^notify:"))
        self.app.add_handler(CallbackQueryHandler(self.notify_set_callback, pattern=r"^notify_set:"))
        self.app.add_handler(CallbackQueryHandler(self.confirm_callback, pattern=r"^confirm:"))

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
        self.scheduler.add_job(func=self.notifier.check_and_notify, trigger="cron", minute="*")

        async def start_scheduler():
            self.scheduler.start()
            logger.info("Scheduler уведомлений запущен (cron каждую минуту.)")

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
            "⏰ Также отправляю уведомления о предстоящих событиях с кнопками "
            "«Уведомить» и «Подтвердить» \n"
        )

        if not update.message:
            return

        await update.message.reply_text(
            text,
            parse_mode="HTML",
            disable_web_page_preview=False,
        )
        logger.info(f"Команда /start от {get_user_id(update.effective_user)}")

    async def notify_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Пользователь нажал кнопку "Уведомить" — показываем варианты времени уведомления.
        """
        query = update.callback_query
        if not (query and query.message):
            return

        await query.answer()
        ev_hash = query.data.split(":")[1]

        session = SessionLocal()
        try:
            record = session.query(SeenEvent).get(ev_hash)
            if not record:
                return

            now = dt.datetime.now(TZINFO)
            minutes_left = max(int((record.start - now).total_seconds() // 60), 0)

            valid_intervals = [m for m in NOTIFY_INTERVALS if m == 0 or m <= minutes_left]

            if not valid_intervals:
                await query.answer("Событие уже начинается", show_alert=True)
                return

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⏱ В момент события" if m == 0 else f"⏱ {m} мин",
                            callback_data=f"notify_set:{ev_hash}:{m}",
                        )
                    ]
                    for m in valid_intervals
                ]
            )

            await query.edit_message_reply_markup(reply_markup=keyboard)

            self.scheduler.add_job(
                func=self._restore_original_buttons,
                trigger="date",
                run_date=now + dt.timedelta(seconds=BUTTON_TTL),
                kwargs={
                    "event_id": ev_hash,
                    "message_id": query.message.message_id,
                },
            )

        finally:
            session.close()

    async def notify_set_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Пользователь выбрал время уведомления — сохраняем next_notify_at.
        Обновляет запись в базе данных и изменяет сообщение в чате.
        Кнопки у сообщения убираем.
        """
        query = update.callback_query
        if not query or not query.message:
            return

        await query.answer()

        _, ev_hash, minutes_str = query.data.split(":")
        minutes = int(minutes_str)

        session = SessionLocal()
        try:
            record = session.query(SeenEvent).get(ev_hash)
            if not record:
                return

            record.next_notify_at = record.start - dt.timedelta(minutes=minutes)
            record.state = EventState.WAITING

            session.commit()

            await query.edit_message_reply_markup(reply_markup=None)

        finally:
            session.close()

    async def confirm_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Пользователь нажал "Подтвердить" — событие подтверждено.
        Обновляет запись в базе данных и изменяет сообщение в чате.
        """
        query = update.callback_query

        if not (query and query.message):
            return

        await query.answer()
        ev_hash = query.data.split(":")[1]

        session = SessionLocal()
        record = session.query(SeenEvent).get(ev_hash)
        if not record:
            return
        try:
            record.state = EventState.CONFIRMED

            text = build_message(
                status=EventStatus.CONFIRMED,
                template=record.message_template,
            )

            await query.edit_message_text(
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=False,
            )
            await query.edit_message_reply_markup(reply_markup=None)

            session.commit()
        finally:
            session.close()

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
        header = f"📅 <b>События <u>{label}</u></b>\n"
        for name, evs in events_dict.items():
            if evs:
                out.append(f"\n👤 <u><b>{name}</b></u>")
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

    async def _restore_original_buttons(self, event_id: str, message_id: int):
        """
         Восстанавливает оригинальные кнопки уведомления и подтверждения, если событие ещё не подтверждено.

        :param event_id: xэш события
        :param message_id: ID сообщения Telegram
        """
        session = SessionLocal()
        try:
            record = session.query(SeenEvent).get(event_id)
            if not record:
                return

            # если уже выбрали таймер / подтвердили — не трогаем
            if record.state != EventState.ANNOUNCED:
                return

            keyboard = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🔔 Уведомить", callback_data=f"notify:{event_id}")],
                    [InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm:{event_id}")],
                ]
            )

            await self.bot_app.bot.edit_message_reply_markup(
                chat_id=NOTIFY_CHAT_ID,
                message_id=message_id,
                reply_markup=keyboard,
            )
        finally:
            session.close()
