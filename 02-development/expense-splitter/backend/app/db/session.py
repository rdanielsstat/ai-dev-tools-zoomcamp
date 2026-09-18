"""Engine/session setup. The only file that knows the concrete database URL —
everything else (store.py, routers) works against a plain SQLAlchemy
`Session` and stays portable across SQLite/Postgres/MySQL/etc."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .base import Base


def make_engine(database_url: str) -> Engine:
    is_sqlite = database_url.startswith("sqlite")
    kwargs: dict[str, object] = {}
    if is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url:
            # A plain in-memory SQLite DB is per-connection; StaticPool keeps
            # every session on the same connection so data isn't lost between
            # requests (used for tests — dev/prod use a file or a real DB).
            kwargs["poolclass"] = StaticPool
    engine = create_engine(database_url, **kwargs)

    if is_sqlite:
        # SQLite ignores FK constraints unless told otherwise per-connection.
        # Postgres/MySQL enforce them by default, so this only matters here —
        # without it, ON DELETE CASCADE on the FKs in models.py would be a no-op.
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection: object, _record: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def make_session_factory(database_url: str) -> sessionmaker[Session]:
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)  # dev convenience; use Alembic migrations for a real deployment
    # autoflush=True (the default) so a query within a method always sees
    # that method's own earlier, not-yet-committed writes; expire_on_commit
    # =False so objects returned from Store methods stay readable (e.g. for
    # response serialization) without an extra round trip after commit().
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_db(request: Request) -> Generator[Session, None, None]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
