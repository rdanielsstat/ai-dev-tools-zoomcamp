from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .db.session import make_session_factory
from .errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError, UnauthorizedError
from .routers import activity, auth, balances, expenses, groups

_ERROR_STATUS: dict[type[Exception], int] = {
    BadRequestError: 400,
    UnauthorizedError: 401,
    ForbiddenError: 403,
    NotFoundError: 404,
    ConflictError: 409,
}

DEFAULT_DATABASE_URL = "sqlite:///./even.db"


def create_app(database_url: str | None = None) -> FastAPI:
    """`database_url` lets tests (and anything else) point at an isolated
    database — see tests/conftest.py. Defaults to DATABASE_URL, or a local
    SQLite file for zero-setup dev. Point DATABASE_URL at Postgres/MySQL/etc.
    to swap the real database; nothing else in the app needs to change."""
    app = FastAPI(title="Even — Expense Splitter API", version="1.0.0")
    resolved_url = database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    app.state.session_factory = make_session_factory(resolved_url)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for exc_class, status_code in _ERROR_STATUS.items():

        def handler(request: Request, exc: Exception, status_code: int = status_code) -> JSONResponse:
            return JSONResponse(status_code=status_code, content={"detail": str(exc)})

        app.add_exception_handler(exc_class, handler)

    for router in (auth.router, groups.router, expenses.router, balances.router, activity.router):
        app.include_router(router, prefix="/api")

    return app


app = create_app()
