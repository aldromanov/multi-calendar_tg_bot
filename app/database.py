import asyncio
import datetime as dt
from enum import Enum

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SAEnum,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config import DATABASE_URL, TZINFO, logger

Base = declarative_base()
engine = create_engine(DATABASE_URL, future=True, echo=False)
SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
    future=True,
)


class EventState(Enum):
    NEW = "new"  #  ещё не отправляли
    ANNOUNCED = "announced"  # отправлено первое сообщение
    WAITING = "waiting"  # ожидаем уведомление
    CONFIRMED = "confirmed"  # подтверждено пользователем
    STARTED = "started"  # событие началось


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

    event_id = Column(String, primary_key=True)
    start = Column(DateTime(timezone=True), nullable=False)
    state = Column(SAEnum(EventState), nullable=False, default=EventState.NEW)
    message_id = Column(Integer, nullable=True)
    message_template = Column(Text, nullable=False)
    next_notify_at = Column(DateTime(timezone=True), nullable=True)


def init_db():
    """
    Инициализирует базу данных, создавая все таблицы, описанные в моделях.
    """
    logger.info("Инициализация базы данных...")
    Base.metadata.create_all(bind=engine)
    logger.info("База данных готова.")


def clean_old_events(session: Session) -> int:
    """
    Удаляет события, которые прошли более недели назад.
    """
    now = dt.datetime.now(TZINFO)
    threshold = now - dt.timedelta(weeks=1)

    old_events = session.query(SeenEvent).filter(SeenEvent.start < threshold).all()
    deleted_count = len(old_events)

    for ev in old_events:
        session.delete(ev)
    if deleted_count:
        session.commit()
        logger.info(f"Очистка БД: удалено {deleted_count} старых событий")
    return deleted_count


async def weekly_cleanup():
    """
    Периодическая асинхронная очистка старых событий раз в неделю.
    """
    while True:
        session = SessionLocal()
        try:
            deleted = clean_old_events(session)
            logger.info(f"Еженедельная очистка: удалено {deleted} старых событий")
        finally:
            session.close()
        await asyncio.sleep(7 * 24 * 60 * 60)
