import datetime as dt

from sqlalchemy.orm import Session
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, error
from telegram.ext import Application

from config import AHEAD_HOUR, TZINFO, logger
from database import EventState, SeenEvent, SessionLocal
from utils import EventStatus, build_message, format_event


class NotifierWorker:
    """
    Класс, который проверяет события в календарях и отправляет уведомления через Telegram.
    """

    def __init__(self, cal_client: object, bot_app: Application, chat_id: str, scheduler):
        """
        Инициализация NotifierWorker.

        :param cal_client: экземпляр MultiCalendarManager или любого объекта с методом list_all_events
        :param bot_app: экземпляр Telegram ApplicationBuilder или объекта с bot.send_message
        :param chat_id: ID чата для отправки уведомлений
        :param scheduler: экземпляр AsyncIOScheduler для планирования задач
        """
        self.cal_client = cal_client
        self.bot_app = bot_app
        self.chat_id = chat_id
        self.scheduler = scheduler
        self.Session = SessionLocal

    async def send_event_notification(
        self,
        session: Session,
        record: SeenEvent,
        status: EventStatus,
        with_buttons: bool,
    ) -> Message:
        """
        Отправляет уведомление о событии в Telegram.

        :param session: SQLAlchemy сессия
        :param record: объект события
        :param status: статус события
        :param with_buttons: нужно ли добавлять кнопки уведомления/подтверждения
        :return: отправляет уведомление о событии в Telegram
        """
        text = build_message(
            status=status,
            template=record.message_template,
        )

        keyboard = None
        if with_buttons:
            keyboard = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🔔 Уведомить", callback_data=f"notify:{record.event_id}")],
                    [InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm:{record.event_id}")],
                ]
            )

        message = await self.bot_app.bot.send_message(
            chat_id=self.chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML",
            disable_web_page_preview=False,
        )

        record.message_id = message.message_id
        session.flush()

        return message

    async def check_and_notify(self) -> None:
        """
        Проверка событий всех календарей и отправка уведомлений о предстоящих событиях.
        """
        logger.info("Проверка событий...")
        now = dt.datetime.now(TZINFO)
        window_end = now + dt.timedelta(hours=AHEAD_HOUR)
        session = self.Session()

        try:
            try:
                all_events = self.cal_client.list_all_events(now, window_end)
            except RuntimeError as e:
                if str(e) == "NEED_REAUTH":
                    await self.bot_app.bot.send_message(
                        chat_id=self.chat_id,
                        text="Google токен истёк или был отозван. Требуется повторная авторизация.",
                    )
                    return
                raise

            for ev in all_events:
                ev_hash = ev.get("ev_hash")
                if not ev_hash:
                    continue

                start_dt = ev.get("start")
                if not start_dt:
                    continue

                start_dt = start_dt.astimezone(TZINFO)
                calendar_name = ev.get("calendar_name", "")

                record = session.query(SeenEvent).get(ev_hash)
                event_text = format_event(ev)
                message_template = f"👤 <u><b>{calendar_name}</b></u>\n{event_text}"

                if not record:
                    record = SeenEvent(
                        event_id=ev_hash,
                        start=start_dt,
                        state=EventState.NEW,
                        message_template=message_template,
                    )
                    session.add(record)

                if record.state == EventState.CONFIRMED:
                    continue

                if start_dt <= now and record.state != EventState.STARTED:
                    record.state = EventState.STARTED
                    await self.send_event_notification(
                        session=session,
                        record=record,
                        status=EventStatus.STARTED,
                        with_buttons=False,
                    )
                    continue

                if record.state == EventState.NEW:
                    record.state = EventState.ANNOUNCED
                    await self.send_event_notification(
                        session=session,
                        record=record,
                        status=EventStatus.ANNOUNCED,
                        with_buttons=True,
                    )

                    self.scheduler.add_job(
                        func=self._auto_start_event,
                        trigger="date",
                        run_date=start_dt,
                        kwargs={"event_id": ev_hash},
                    )

                if record.state == EventState.WAITING and record.next_notify_at:
                    if now >= record.next_notify_at:
                        await self.send_event_notification(
                            session=session,
                            record=record,
                            status=EventStatus.SOON,
                            with_buttons=True,
                        )
                        record.next_notify_at = None

            session.commit()
        finally:
            session.close()
            logger.info("Проверка событий завершена.")

    async def _auto_start_event(self, event_id: str) -> None:
        """
        Автоматическая обработка события при наступлении времени.
        Меняет сообщение на 'Событие началось' и убирает кнопки, если пользователь не взаимодействовал.

        :param event_id: xэш события для поиска в БД.
        """
        session = self.Session()
        try:
            record = session.query(SeenEvent).get(event_id)
            if not record or record.state in {EventState.CONFIRMED, EventState.STARTED}:
                return

            text = build_message(
                status=EventStatus.SOON,
                template=record.message_template,
            )
            try:
                await self.bot_app.bot.edit_message_text(
                    chat_id=self.chat_id,
                    message_id=record.message_id,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=False,
                )
            except error.BadRequest as e:
                if "Message is not modified" not in str(e):
                    raise

            try:
                await self.bot_app.bot.edit_message_reply_markup(
                    chat_id=self.chat_id,
                    message_id=record.message_id,
                    reply_markup=None,
                )
            except error.BadRequest as e:
                if "Message is not modified" not in str(e):
                    raise

            record.state = EventState.STARTED
            session.commit()
        finally:
            session.close()
