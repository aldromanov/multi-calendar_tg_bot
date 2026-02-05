import json
import logging
import os

from urllib.parse import quote_plus
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

# Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("calendar_bot")

# Telegram
TELEGRAM_TOKEN: str | None = os.environ.get("TELEGRAM_TOKEN")
NOTIFY_CHAT_ID: str | None = os.environ.get("NOTIFY_CHAT_ID")

if not TELEGRAM_TOKEN or not NOTIFY_CHAT_ID:
    logger.error("TELEGRAM_TOKEN и NOTIFY_CHAT_ID должны быть установлены в окружении")
    raise ValueError("Отсутствуют обязательные переменные окружения")

# Google Calendar
TOKENS_PATH: str = os.environ.get("TOKENS_PATH", "/app/tokens")
RAW_CALENDAR_TOKENS: str = os.environ.get("CALENDAR_TOKENS", "{}")
CALENDAR_TOKENS: dict = json.loads(RAW_CALENDAR_TOKENS)

# Scheduler / timing settings
AHEAD_HOUR: int = int(os.environ.get("AHEAD_HOUR", "2"))
BUTTON_TTL: int = int(os.environ.get("BUTTON_TTL", "30"))
NOTIFY_INTERVALS = [int(x) for x in os.getenv("NOTIFY_INTERVALS", "60,30,15,10,5,0").split(",")]

# Timezone
TIMEZONE: str = os.environ.get("TIMEZONE", "Europe/Moscow")
TZINFO = ZoneInfo(TIMEZONE)

# Postgres
POSTGRES_DB: str = os.environ.get("POSTGRES_DB", "calendar_db")
POSTGRES_USER: str = os.environ.get("POSTGRES_USER", "calendar_user")
POSTGRES_PASSWORD: str = os.environ.get("POSTGRES_PASSWORD", "securepassword")
POSTGRES_HOST: str = os.environ.get("POSTGRES_HOST", "db")
POSTGRES_PORT: str = os.environ.get("POSTGRES_PORT", "5432")

POSTGRES_PASSWORD_ENCODED: str = quote_plus(POSTGRES_PASSWORD)

DB_URL: str = f"{POSTGRES_USER}:{POSTGRES_PASSWORD_ENCODED}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    f"postgresql+psycopg2://{DB_URL}",
)

# Google API scopes
SCOPES: list[str] = ["https://www.googleapis.com/auth/calendar.readonly"]

# RU weekday
WEEKDAY = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}
