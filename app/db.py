"""Database engine, session factory and schema bootstrap."""
from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs() -> dict:
    if settings.is_sqlite:
        path = settings.database_url.split("///", 1)[-1]
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        # wait for the writer rather than failing instantly, the collector
        # holds transactions open for seconds
        return {"connect_args": {"check_same_thread": False, "timeout": 30}}
    return {"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20}


engine = create_engine(settings.database_url, future=True, **_engine_kwargs())

if settings.is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):
        """SQLite only. Without WAL a collection run locks out every reader
        and page loads fail with 'database is locked'."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")      # readers never block on a writer
        cursor.execute("PRAGMA busy_timeout=30000")    # queue for 30s rather than fail
        cursor.execute("PRAGMA synchronous=NORMAL")    # safe under WAL, far fewer fsyncs
        cursor.execute("PRAGMA foreign_keys=ON")       # honour the ON DELETE CASCADEs
        cursor.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _email_index_is_unique(conn) -> bool | None:
    """True, False, or None if there is no such index."""
    if settings.is_sqlite:
        rows = conn.exec_driver_sql("PRAGMA index_list('users')").fetchall()
        for row in rows:
            if row[1] == "ix_users_email":
                return bool(row[2])
        return None
    row = conn.exec_driver_sql(
        "SELECT indisunique FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
        "WHERE c.relname = 'ix_users_email'"
    ).fetchone()
    return None if row is None else bool(row[0])


def apply_migrations() -> None:
    """Schema fixes create_all cannot do.

    create_all only adds missing tables, it never alters an existing one, so a
    constraint that outlived its purpose has to go by hand. Everything here
    checks the live schema first and is safe to run on every boot.
    """
    from sqlalchemy import text

    with engine.begin() as conn:
        if not conn.dialect.has_table(conn, "users"):
            return

        # Sign-up asks for a name and a password, so most accounts have no
        # email. A unique index would allow exactly one of them.
        if _email_index_is_unique(conn) is True:
            conn.execute(text("DROP INDEX ix_users_email"))
            conn.execute(text("CREATE INDEX ix_users_email ON users (email)"))


def init_db() -> None:
    from . import models  # noqa: F401  (registers the mappers)

    Base.metadata.create_all(bind=engine)
    apply_migrations()
