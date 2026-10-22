from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


def create_db_engine(settings: Settings) -> Engine:
    engine = create_engine(settings.database_url, connect_args={
        'check_same_thread': False,
        'autocommit': False,
        'timeout': 30,
    })

    @event.listens_for(engine, 'connect')
    def enable_foreign_keys(connection, _record):
        previous = connection.autocommit
        connection.autocommit = True
        cursor = connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()
        connection.autocommit = previous

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
