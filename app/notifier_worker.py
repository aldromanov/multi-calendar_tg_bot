import datetime as dt

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

from config import TZINFO, logger, BUTTON_TTL, AHEAD_MINUTES, REPEAT_MINUTES
from database import SessionLocal, SeenEvent
from utils import format_event


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

    async def send_event_notification(self, ev: dict, name: str, session, icon: str) -> None:
        """
        Отправка уведомления о событии в Telegram с кнопкой подтверждения.
        """
        ev_hash = ev.get("ev_hash")
        record = session.query(SeenEvent).filter_by(event_id=ev_hash).first()
        if record and record.confirmed:
            session.close()
            return

        event_text = format_event(ev)
        html_text = f"{icon} <b>Скоро событие</b>\n\n👤 <u><b>{name}</b></u>\n{event_text}"
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Подтвердить", callback_data=ev_hash)],
            ]
        )

        message = await self.bot_app.bot.send_message(
            chat_id=self.chat_id,
            text=html_text,
            reply_markup=keyboard,
            parse_mode="HTML",
            disable_web_page_preview=False,
        )

        self.scheduler.add_job(
            self.bot_app.bot.edit_message_reply_markup,
            "date",
            run_date=dt.datetime.now() + dt.timedelta(seconds=BUTTON_TTL),
            kwargs={
                "chat_id": self.chat_id,
                "message_id": message.message_id,
                "reply_markup": None,
            },
        )
        logger.info(f"Задача удаления кнопки через {BUTTON_TTL} сек добавлена для {ev_hash}")

    async def check_and_notify(self) -> None:
        """
        Проверка событий всех календарей и отправка уведомлений о предстоящих событиях.
        """
        logger.info("Проверка событий...")
        now = dt.datetime.now(TZINFO)
        window_end = now + dt.timedelta(minutes=AHEAD_MINUTES)
        session = self.Session()

        try:
            all_events = self.cal_client.list_all_events(now, window_end)
            for ev in all_events:
                ev_hash = ev.get("ev_hash")
                name = f"{ev.get('calendar_name')}"
                if not ev_hash:
                    continue

                record = session.query(SeenEvent).filter_by(event_id=ev_hash).first()

                start_raw = ev.get("start")
                if not start_raw:
                    continue

                start_dt = start_raw.astimezone(TZINFO)
                send_again = False
                icon = "⏰"

                if now <= start_dt <= window_end:
                    if record:
                        if not record.confirmed:
                            delta = now - record.notified_at.astimezone(TZINFO)
                            if delta.total_seconds() >= REPEAT_MINUTES * 60:
                                send_again = True
                                icon = "⚡"
                    else:
                        send_again = True

                if send_again:
                    await self.send_event_notification(ev, name, session, icon)
                    if record:
                        record.notified_at = now
                        record.notified = True
                    else:
                        new_record = SeenEvent(
                            event_id=ev_hash,
                            notified=True,
                            confirmed=False,
                            notified_at=now,
                        )
                        session.add(new_record)

            session.commit()
        finally:
            session.close()
            logger.info("Проверка событий завершена.")
