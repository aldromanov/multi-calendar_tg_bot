import datetime as dt

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

from config import TZINFO, logger, BUTTON_TTL, AHEAD_HOUR
from database import SessionLocal, SeenEvent
from utils import format_event, get_notify_time


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

    async def send_event_notification(self, ev: dict, name: str, session, icon: str, confirmable: bool) -> None:
        """
        Отправка уведомления о событии в Telegram с кнопкой подтверждения.
        """
        ev_hash = ev.get("ev_hash")
        record = session.query(SeenEvent).filter_by(event_id=ev_hash).first()
        if record and record.confirmed:
            session.close()
            return

        event_text = format_event(ev)
        label = "<b>Cобытие началось</b>" if icon == "🆘" else "<b>Скоро событие</b>"
        html_text = f"{icon} {label}\n\n👤 <u><b>{name}</b></u>\n{event_text}"
        keyboard = None
        if confirmable:
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

        if confirmable:
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
                name = f"{ev.get('calendar_name')}"
                if not ev_hash:
                    continue

                record = session.query(SeenEvent).filter_by(event_id=ev_hash).first()

                start_raw = ev.get("start")
                if not start_raw:
                    continue
                start_dt = start_raw.astimezone(TZINFO)

                if record and record.confirmed:
                    continue

                minutes_left = int((start_dt - now).total_seconds() / 60)
                if minutes_left < 0:
                    continue

                send = False
                confirmable = False
                icon = "⏰"

                all_points = get_notify_time(AHEAD_HOUR)
                next_point = next_point = next((p for p in all_points if p == minutes_left), None)

                if next_point is not None:
                    if not record or record.last_point is None or next_point < record.last_point:
                        send = True
                        if not record:
                            record = SeenEvent(
                                event_id=ev_hash,
                                start=start_dt,
                                last_point=next_point,
                                notified_at=start_dt - dt.timedelta(minutes=next_point),
                                confirmed=False,
                            )
                            session.add(record)
                        else:
                            record.last_point = next_point
                            record.notified_at = start_dt - dt.timedelta(minutes=next_point)

                if minutes_left > 60:
                    icon = "⏰"
                    confirmable = False
                elif 0 < minutes_left <= 30:
                    icon = "⚡"
                    confirmable = True
                elif minutes_left == 0:
                    icon = "🆘"
                    confirmable = False

                if send:
                    await self.send_event_notification(ev, name, session, icon, confirmable)

            session.commit()
        finally:
            session.close()
            logger.info("Проверка событий завершена.")

    @staticmethod
    def format_confirmed_message(original_text: str) -> str:
        """
        Возвращает отформатированный текст подтверждённого события.
        """
        parts = original_text.split("\n", 4)
        header = parts[0].replace("⚡ Скоро событие", "🎯 <b>Событие подтверждено</b>")
        sub = parts[2].split(" ", 1)
        sub_header = f"{sub[0]} <u><b>{sub[1]}</b></u>"
        text = f"<code>{parts[3]}</code>"
        return f"{header}\n\n{sub_header}\n{text}"
