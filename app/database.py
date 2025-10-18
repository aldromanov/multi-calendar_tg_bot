import datetime

from sqlalchemy import create_engine, Column, String, DateTime, Boolean, Integer
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
    Модель для хранения информации о событиях и статусе уведомлений.

    Attributes:
        event_id (str): Уникальный идентификатор события.
        start (datetime): Время начала события.
        notified_at (datetime): Время, когда было отправлено уведомление.
        last_point (int, optional): Последняя точка уведомления в минутах до события, для которой уже отправлено уведомление.
        confirmed (bool): Статус подтверждения события. True, если пользователь подтвердил событие.
    """

    __tablename__ = "seen_events"
    event_id = Column(String, primary_key=True, index=True)
    start = Column(DateTime(timezone=True))
    notified_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(TZINFO),
    )
    last_point = Column(Integer, nullable=True)
    confirmed = Column(Boolean, default=False)


def init_db():
    """
    Инициализирует базу данных, создавая все таблицы, описанные в моделях.
    """
    logger.info("Инициализация базы данных...")
    Base.metadata.create_all(bind=engine)
    logger.info("База данных готова.")
