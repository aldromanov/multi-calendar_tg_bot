import datetime as dt
from enum import Enum

from config import TZINFO, WEEKDAY


class EventStatus(Enum):
    ANNOUNCED = ("⏰", "Событие")
    SOON = ("⚡", "Скоро событие")
    STARTED = ("🆘", "Событие началось")
    CONFIRMED = ("🎯", "Событие подтверждено")

    @property
    def header(self) -> str:
        icon, text = self.value
        return f"{icon} <b>{text}</b>"


def format_event(ev: dict, name_width: int = 25) -> str:
    """
    Docstring for format_event

    :param ev: cобытие календаря.
    :param name_width: максимальное кол-во символов в названии события
    :return: отформатированная строка события с датой, временем и значком.
    """
    start: dt.datetime = ev["start"]
    start = start.astimezone(TZINFO)
    now = dt.datetime.now(TZINFO)
    mark = "☑️" if start < now else "📌"

    start_str = start.strftime("%d.%m %H:%M")
    weekday_str = WEEKDAY[start.weekday()]

    summary = ev.get("summary", "(без названия)")
    if len(summary) > name_width:
        summary = summary[: name_width - 3] + "..."

    summary_padded = summary.ljust(name_width)

    return f"<code>{mark} {start_str} ({weekday_str}) | {summary_padded}</code>"


def build_message(status: EventStatus, template: str) -> str:
    """
    Формирует сообщение Telegram с заголовком статуса события.

    :param status: cтатус события.
    :param template: шаблон текста события
    :return: полный текст сообщения
    """
    return f"{status.header}\n\n{template}"


def get_user_id(user) -> str:
    """
    Возвращает строковое представление пользователя Telegram.

    :param user: Объект пользователя Telegram.
    :return: формат 'username (id)'
    """
    username = getattr(user, "username", "anon")
    id = getattr(user, "id", "0")
    return f"{username} ({id})"
