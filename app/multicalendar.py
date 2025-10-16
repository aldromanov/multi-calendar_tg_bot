import os
from typing import Dict, List, Any

from config import logger, TOKENS_PATH
from google_calendar import GoogleCalendarClient


class MultiCalendarManager:
    def __init__(self, configs: Dict[str, Dict[str, Any]]):
        """
        Инициализация менеджера нескольких календарей.

        :param configs: словарь конфигураций пользователей,
                        где ключ — имя пользователя,
                        значение — словарь с ключами 'token' и 'calendars'
        """
        self.clients: Dict[str, Dict[str, Any]] = {}
        self._init_clients(configs)

    def _create_client_for_user(self, user: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Создает клиента Google Calendar для одного пользователя.

        :param user: имя пользователя
        :param data: словарь с данными пользователя, включая 'token' и 'calendars'
        :return: словарь с ключами 'client' и 'calendars'
        """
        token_path = os.path.join(TOKENS_PATH, data.get("token"))
        calendars = data.get("calendars", {})
        client = GoogleCalendarClient(token_path=token_path)
        logger.info(f"Добавлен календарь пользователя {user} ({len(calendars)} календарей)")
        return {"client": client, "calendars": calendars}

    def _init_clients(self, configs: Dict[str, Dict[str, Any]]) -> None:
        """
        Инициализирует всех клиентов для пользователей из конфигурации.

        :param configs: словарь конфигураций пользователей
        """
        for user, data in configs.items():
            self.clients[user] = self._create_client_for_user(user, data)

    def list_all_events(self, start: str, end: str) -> List[Dict[str, Any]]:
        """
        Получает все события всех пользователей в заданном диапазоне дат.

        :param start: дата начала в формате строки
        :param end: дата окончания в формате строки
        :return: список событий всех пользователей
        """
        all_events = []
        for cfg in self.clients.values():
            client = cfg["client"]
            for name, cid in cfg["calendars"].items():
                events = client.list_events_between(cid, start, end)
                for ev in events:
                    ev["calendar_name"] = name
                    all_events.append(ev)
        return all_events
