from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        if url.startswith("sqlite:///") and url != "sqlite:///:memory:":
            from pathlib import Path

            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        extra = {"poolclass": StaticPool} if url == "sqlite:///:memory:" else {}
        engine = create_engine(url, connect_args={"check_same_thread": False}, **extra)

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # SQLite ignores FKs unless asked
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
            dbapi_conn.execute("PRAGMA journal_mode=WAL")

        return engine
    return create_engine(url, pool_pre_ping=True)


def init_db(engine: Engine) -> None:
    # Fine for SQLite and a young schema. Switch to Alembic before the first
    # migration that has to preserve production data.
    Base.metadata.create_all(engine)


class Database:
    def __init__(self, url: str):
        self.engine = make_engine(url)
        init_db(self.engine)
        self.sessionmaker = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Iterator[Session]:
        with self.sessionmaker() as s:
            yield s
