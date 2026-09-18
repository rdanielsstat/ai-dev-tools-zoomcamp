# Even — Expense Splitter

Even tracks shared spending across a group — a trip, an apartment, a dinner
club — and computes the smallest set of payments that settles every debt.
Log an expense with whatever split makes sense (equal, exact amounts,
percentages, shares, or itemized line items), and Even keeps a running
balance per person plus a settle-up plan with as few payments as possible.

Full product spec: [`_docs/specs.md`](_docs/specs.md).

## Project layout

```
.
├── openapi.yaml     # REST API contract — source of truth for both frontend and backend
├── _docs/           # Product spec
├── frontend/        # React + TanStack Start SPA
└── backend/         # FastAPI service (SQLAlchemy, SQLite by default)
```

The frontend and backend are independent apps that only ever talk to each
other over the HTTP API described in `openapi.yaml`.

## Tech stack

| | |
|---|---|
| **Frontend** | React 19, TanStack Start / Router / Query, Tailwind CSS, Vite, TypeScript, Vitest |
| **Backend** | FastAPI, SQLAlchemy 2.0, Pydantic, pytest, [uv](https://docs.astral.sh/uv/) |
| **Database** | SQLite by default (`backend/even.db`, created automatically); swap in Postgres/MySQL/etc. via `DATABASE_URL` — nothing else in the app needs to change |

## Getting started

You need [Node.js](https://nodejs.org/) (or [bun](https://bun.sh/)) for the
frontend and [uv](https://docs.astral.sh/uv/) for the backend. Run both —
the frontend won't work without the backend behind it.

### Backend

```bash
cd backend
uv run uvicorn app.main:app --reload
```

Serves on `http://localhost:8000`. Interactive API docs (Swagger UI) at
`http://localhost:8000/docs` — useful for poking at the API directly, or for
grabbing a bearer token to test with (`POST /auth/login`, then the
**Authorize** button).

A SQLite file (`backend/even.db`) is created on first run and persists
between restarts. Delete it to start from a clean database.

### Frontend

```bash
cd frontend
npm run dev
```

Serves on `http://localhost:8080` (Vite picks the next free port if that one's
taken — check the terminal output). Points at the backend via
`VITE_API_URL`, which defaults to `http://localhost:8000/api`; copy
`frontend/.env.example` to `frontend/.env.local` to override it.

There's no seed data — sign up for a fresh account on first visit.

## Testing

```bash
# Backend — unit tests for the split/settlement math, and endpoint tests
# through the full HTTP stack (see backend/tests/)
cd backend && uv run pytest

# Frontend — split/settlement math, plus the API client's HTTP plumbing
# against a mocked fetch (see frontend/src/lib/*.test.ts)
cd frontend && npm run test
```

## API

`openapi.yaml` at the repo root is the contract both apps are built against:
every endpoint, request/response shape, and which ones require
authentication (all of them except `/auth/signup` and `/auth/login`, via a
bearer token). The backend's implementation is checked against it directly —
`backend/tests/test_openapi_contract.py` fails if the two drift apart.

## Notes

- **Money** is always integer cents, never floats — splits are guaranteed to
  reconcile exactly to the expense total, with any rounding remainder
  distributed deterministically.
- **Settling up** uses a greedy debt-simplification algorithm
  (`backend/app/money.py`, mirrored in `frontend/src/lib/money.ts`): largest
  debtor pays largest creditor until everyone's at zero, which never takes
  more than *n − 1* payments for *n* group members.
