import datetime as dt
import hashlib
import os
import pickle
from typing import List, Dict

from googleapiclient.discovery import build, Resource
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError

from config import TZINFO, logger


class GoogleCalendarClient:
    """
    Клиент для работы с Google Calendar API через pickle-токен.
    """

    def __init__(self, token_path: str, tz: dt.tzinfo = TZINFO):
        self.token_path: str = token_path
        self.creds: object | None = None
        self.service: Resource | None = None
        self.tz: dt.tzinfo = tz
        self._authorize()

    def _authorize(self) -> None:
        logger.info("Авторизация Google Calendar API...")
        if not os.path.exists(self.token_path):
            raise FileNotFoundError(
                f"Файл токена не найден: {self.token_path}. Создайте его с помощью get_token_pickle.py"
            )

        with open(self.token_path, "rb") as f:
            self.creds = pickle.load(f)
        self.service = build("calendar", "v3", credentials=self.creds)
        logger.info("Google Calendar API клиент готов к работе.")

    def _save_creds(self):
        with open(self.token_path, "wb") as f:
            pickle.dump(self.creds, f)

    def _ensure_token(self) -> None:
        if self.creds is None:
            self._authorize()
            return

        # expired → пробуем обновить
        if self.creds.expired and self.creds.refresh_token:
            try:
                self.creds.refresh(Request())
                self._save_creds()
                self.service = build("calendar", "v3", credentials=self.creds)

            except RefreshError as e:
                logger.error(f"RefreshError: {e}")
                raise RuntimeError("NEED_REAUTH")

        # если refresh_token отсутствует или токен битый
        if not self.creds.valid:
            raise RuntimeError("NEED_REAUTH")

    def list_events_between(
        self,
        calendar_id: str,
        start: dt.datetime,
        end: dt.datetime,
    ) -> List[Dict]:
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

    def get_events_for_day(self, calendar_id: str, day: dt.date) -> List[Dict]:
        start, end = self._get_range_for_day(day)
        return self.list_events_between(calendar_id, start, end)

    def get_events_for_week(self, calendar_id: str, start_date: dt.date) -> List[Dict]:
        start, _ = self._get_range_for_day(start_date)
        end = (start + dt.timedelta(days=7)).replace(tzinfo=self.tz)
        return self.list_events_between(calendar_id, start, end)

    def _parse_datetime(self, event: dict, key: str) -> dt.datetime:
        val = event.get(key, {}).get("dateTime") or event.get(key, {}).get("date")
        if len(val) == 10:
            return dt.datetime.fromisoformat(val).replace(tzinfo=self.tz)
        return dt.datetime.fromisoformat(val)

    def _get_range_for_day(self, day: dt.date) -> tuple[dt.datetime, dt.datetime]:
        start = dt.datetime.combine(day, dt.time.min).replace(tzinfo=self.tz)
        end = dt.datetime.combine(day, dt.time.max).replace(tzinfo=self.tz)
        return start, end
