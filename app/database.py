import datetime as dt

import asyncio
from sqlalchemy import create_engine, Column, String, DateTime, Boolean, Integer
from sqlalchemy.orm import declarative_base, sessionmaker, Session

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
        default=lambda: dt.datetime.now(TZINFO),
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
    while True:
        session = SessionLocal()
        try:
            deleted = clean_old_events(session)
            logger.info(f"Еженедельная очистка: удалено {deleted} старых событий")
        finally:
            session.close()
        await asyncio.sleep(7 * 24 * 60 * 60)
