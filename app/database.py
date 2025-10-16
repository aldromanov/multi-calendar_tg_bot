import datetime

from sqlalchemy import create_engine, Column, String, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker

from config import DATABASE_URL, logger, TZINFO

Base = declarative_base()
engine = create_engine(DATABASE_URL, future=True, echo=False)
SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
    future=True,
)


class SeenEvent(Base):
    """
    Модель для хранения событий, о которых уже уведомили.

    Attributes:
        event_id (str): ID события.
        notified_at (datetime): Время уведомления.
        notified (bool): Статус уведомления.
        confirmed (bool): Статус подтверждения.
    """

    __tablename__ = "seen_events"
    event_id = Column(String, primary_key=True, index=True)
    notified_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(TZINFO),
    )
    notified = Column(Boolean, default=False)
    confirmed = Column(Boolean, default=False)


def init_db():
    """
    Инициализирует базу данных, создавая все таблицы, описанные в моделях.
    """
    logger.info("Инициализация базы данных...")
    Base.metadata.create_all(bind=engine)
    logger.info("База данных готова.")
