import datetime as dt
import hashlib
import os
import pickle

from googleapiclient.discovery import build, Resource
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError

from config import TZINFO, logger


class GoogleCalendarClient:
    """
    Клиент для работы с Google Calendar API через pickle-токен.

    Использует pickle-файл с OAuth-токеном, автоматически обновляет access token
    и предоставляет методы получения событий за день и неделю.
    """

    def __init__(self, token_path: str, tz: dt.tzinfo = TZINFO) -> None:
        """
        Инициализирует клиента Google Calendar.

        :param token_path: путь к pickle-файлу с OAuth-токеном
        :param tz: таймзона для обработки дат и времени.
        """
        self.token_path: str = token_path
        self.creds: object | None = None
        self.service: Resource | None = None
        self.tz: dt.tzinfo = tz
        self._authorize()

    def _authorize(self) -> None:
        """
        Загружает токен из pickle-файла и инициализирует Google Calendar API сервис.
        """
        logger.info("Авторизация Google Calendar API...")
        if not os.path.exists(self.token_path):
            raise FileNotFoundError(
                f"Файл токена не найден: {self.token_path}. Создайте его с помощью get_token_pickle.py"
            )

        with open(self.token_path, "rb") as f:
            self.creds = pickle.load(f)
        self.service = build("calendar", "v3", credentials=self.creds)
        logger.info("Google Calendar API клиент готов к работе.")

    def _save_creds(self) -> None:
        """
        Сохраняет обновлённые OAuth-учётные данные обратно в pickle-файл.
        """
        with open(self.token_path, "wb") as f:
            pickle.dump(self.creds, f)

    def _ensure_token(self) -> None:
        """
        Проверяет валидность OAuth-токена и при необходимости обновляет его.
        """
        if self.creds is None:
            self._authorize()
            return

        if self.creds.expired and self.creds.refresh_token:
            try:
                self.creds.refresh(Request())
                self._save_creds()
                self.service = build("calendar", "v3", credentials=self.creds)

            except RefreshError as e:
                logger.error(f"RefreshError: {e}")
                raise RuntimeError("NEED_REAUTH")

        if not self.creds.valid:
            raise RuntimeError("NEED_REAUTH")

    def list_events_between(
        self,
        calendar_id: str,
        start: dt.datetime,
        end: dt.datetime,
    ) -> list[dict]:
        """
        Возвращает список событий календаря в заданном диапазоне времени.

        :param calendar_id: ID календаря Google.
        :param start: начало интервала
        :param end: конец интервала.
        :return: список подходящих событий
        """
        if not self.service:
            raise ValueError("Google API клиент не инициализирован")

        self._ensure_token()

        time_min = start.astimezone(self.tz).isoformat()
        time_max = end.astimezone(self.tz).isoformat()

        events_result = (
            self.service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        items = events_result.get("items", [])
        out = []
        for e in items:
            start_dt = self._parse_datetime(event=e, key="start")
            end_dt = self._parse_datetime(event=e, key="end")

            hash_str = hashlib.md5(f"{e.get('id')}_{start_dt}".encode())
            out.append(
                {
                    "ev_hash": hash_str.hexdigest()[:16],
                    "summary": e.get("summary", "(без названия)"),
                    "start": start_dt,
                    "end": end_dt,
                }
            )
        logger.info(f"Получено {len(out)} событий из календаря {calendar_id}")
        return out

    def get_events_for_day(self, calendar_id: str, day: dt.date) -> list[dict]:
        """
        Возвращает события календаря за указанный день.

        :param calendar_id: ID календаря Google.
        :param day: дата дня
        :return: список событий за день
        """
        start, end = self._get_range_for_day(day)
        return self.list_events_between(calendar_id, start, end)

    def get_events_for_week(self, calendar_id: str, start_date: dt.date) -> list[dict]:
        """
        Возвращает события календаря за 7 дней.

        :param calendar_id: ID календаря Google.
        :param day: дата начала недели
        :return: список событий за неделю
        """
        start, _ = self._get_range_for_day(start_date)
        end = (start + dt.timedelta(days=7)).replace(tzinfo=self.tz)
        return self.list_events_between(calendar_id, start, end)

    def _parse_datetime(self, event: dict, key: str) -> dt.datetime:
        """
        Парсит дату и время события Google Calendar.
        Поддерживает как dateTime, так и all-day события (date).

        :param event: события Google календаря
        :param key: ключ 'start'
        :return: время события с таймзоной
        """
        val = event.get(key, {}).get("dateTime") or event.get(key, {}).get("date")
        if len(val) == 10:
            return dt.datetime.fromisoformat(val).replace(tzinfo=self.tz)
        return dt.datetime.fromisoformat(val)

    def _get_range_for_day(self, day: dt.date) -> tuple[dt.datetime, dt.datetime]:
        """
        Возвращает временной диапазон для одного дня.

        :param day: дата дня
        :return: начало и конец дня в заданной таймзоне.
        """
        start = dt.datetime.combine(day, dt.time.min).replace(tzinfo=self.tz)
        end = dt.datetime.combine(day, dt.time.max).replace(tzinfo=self.tz)
        return start, end
