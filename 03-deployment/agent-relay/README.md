# Agent Relay (SQLite starter)

Agent Relay is a small FastAPI service for registering agents, delivering one
task at a time, and recording results. The local starter is self-contained:
SQLite persists the queue and attempts, while workers execute tasks on their own
machines. The included worker deterministically returns `input.upper()`.

## Run it

```bash
uv sync
uv run uvicorn main:app --reload
```

Open <http://127.0.0.1:8000/> for the token-based local dashboard. The default
database is `./agent-relay.db`; set `RELAY_DATABASE_URL` to use another SQLite
file. `GET /health` is a liveness check and `GET /ready` verifies database
connectivity and schema (it queries the real tables, so a wiped volume
reports not-ready instead of passing with zero tables).

Register two identities and send a task:

```bash
alice=$(curl -sS -X POST http://127.0.0.1:8000/api/v1/agents \
  -H 'content-type: application/json' -d '{"name":"alice"}')
bob=$(curl -sS -X POST http://127.0.0.1:8000/api/v1/agents \
  -H 'content-type: application/json' -d '{"name":"uppercase"}')
```

The response contains each agent's secret `token` once. Keep it outside source
control. Use `Authorization: Bearer <token>` for all subsequent API calls;
registration is the only unauthenticated endpoint. For a shared installation,
set `RELAY_ENROLLMENT_SECRET` and send it as `X-Enrollment-Secret` when
registering.

## Run the deterministic worker

The worker can register itself and save credentials in a mode-0600 JSON file:

```bash
uv run python main.py worker \
  --base-url http://127.0.0.1:8000 \
  --name uppercase \
  --credentials ./uppercase-credentials.json \
  --worker-id laptop-1
```

For failure/redelivery demonstrations, make local execution intentionally slow
and stop the process after one completion:

```bash
uv run python main.py worker --credentials ./uppercase-credentials.json \
  --slow-seconds 75 --worker-id slow-laptop
```

The worker heartbeats during long work. Killing it leaves the claim leased;
after the 60-second lease expires, another worker can claim the task with a new
token and incremented attempt number. `RELAY_LEASE_SECONDS` and
`RELAY_MAX_ATTEMPTS` are configurable server settings.

An existing credential can also be supplied explicitly (the token is not
written to disk):

```bash
uv run python main.py worker --agent-id agent_123 --token agt_… --worker-id laptop-2
```

## Storage and delivery behavior

`database.py` contains SQLAlchemy models, SQLite WAL setup, and the isolated
`BEGIN IMMEDIATE` transaction helper. `storage.py` contains task/claim/recovery
operations; routes and request models are kept in `main.py` and `schemas.py`.
SQLite has no row-level locking, so the starter serializes writer transactions
(`BEGIN IMMEDIATE`) to make concurrent claims safe across processes. On
PostgreSQL (see below) the same functions instead take row-level locks —
`SELECT ... FOR UPDATE`, and `FOR UPDATE SKIP LOCKED` for the claim query —
chosen automatically from the `RELAY_DATABASE_URL` scheme, with no change to
the HTTP protocol or lifecycle in `SPEC.md`.

Claims are at-least-once and leased for 60 seconds by default. Heartbeats extend
an active lease. A completion or failure must include the recipient's bearer
token and claim token. Repeating the exact terminal request with that claim
token is idempotent; a stale token or different result receives `409`.

## Run it with Docker

```bash
docker build -t agent-relay:local .
docker run -d --name agent-relay -p 8000:8000 agent-relay:local
```

The image runs `uvicorn --host 0.0.0.0`; `--host 127.0.0.1` (uvicorn's
default) would only accept connections from inside the container and make
`-p` look broken. The API and dashboard behave identically to the local run.
SQLite data lives inside the container's writable layer unless you mount a
volume, so it's lost on `docker rm`.

## Run it with PostgreSQL (Docker Compose)

`compose.yaml` runs the API alongside a `postgres` service:

```bash
docker compose up --build
```

No code differs between backends: `RELAY_DATABASE_URL`'s scheme picks SQLite
or PostgreSQL (`postgresql+psycopg://user:pass@postgres:5432/agent_relay`),
which selects the locking strategy described above. Inside the compose
network the API reaches the database at the service name `postgres`,
resolved by Docker's built-in DNS — not `localhost`.

## Deploy to Kubernetes (kind)

Manifests live in `k8s/`: a `postgres` `Deployment` (PVC-backed storage,
`pg_isready` readiness/liveness) and an `agent-relay-api` `Deployment` (2
replicas, `/ready` and `/health` probes, an `initContainer` that waits for
PostgreSQL since Kubernetes has no `depends_on`), each behind its own
`Service`.

```bash
kind create cluster --name agent-relay
docker build -t agent-relay:local .
kind load docker-image agent-relay:local --name agent-relay
kubectl apply -f k8s/
kubectl -n agent-relay rollout status deployment/agent-relay-api
kubectl -n agent-relay port-forward svc/agent-relay-api 8000:8000
```

A `Deployment` is the resource that keeps the requested replica count
running and manages rollouts (through an owned `ReplicaSet`); `kubectl set
image` or an edited manifest triggers a controlled rolling update rather
than pods being managed by hand.

## Continuous integration

`.github/workflows/ci.yml` runs the SQLite test suite plus an HTTP
integration test against a real PostgreSQL service container, then — only
if both pass (the deploy job `needs: test`) — builds a uniquely tagged
image, loads it into the `agent-relay` kind cluster, and waits for the
rollout. If a test fails, the deploy job never runs and the cluster keeps
serving whatever was already deployed; nothing gets rolled forward, deleted,
or rolled back automatically.

Run it locally against an already-running kind cluster with
[`act`](https://github.com/nektos/act):

```bash
act workflow_dispatch -W .github/workflows/ci.yml \
  -P ubuntu-latest=catthehacker/ubuntu:act-latest -b
```

`act`'s job containers run in Docker's `--network host` mode by default, so
the PostgreSQL service is reached via `localhost:5432` (not a service-name
hostname), and the deploy job can read the same `127.0.0.1`-based kubeconfig
`kind` already writes on the host.

## Verify

The test suite covers the main protocol, sender/recipient access boundaries,
hashed claim-token behavior, idempotent terminal retries, concurrent claims,
lease expiry before and after recovery, pagination/error shape, and dashboard
asset serving:

```bash
uv run pytest -q
```

Tests default to a scratch database at `/tmp/agent-relay-test.db` so they
don't reset your dev server's `./agent-relay.db`. The fixture drops and
recreates all tables on whatever `RELAY_DATABASE_URL` points at, so stop
the dev server first or set `RELAY_DATABASE_URL` to a scratch file before
running tests against another database.

`test_live_api_integration.py` separately drives a real running server over
real HTTP instead of FastAPI's in-process `TestClient`. By default it
launches its own SQLite-backed `uvicorn` subprocess; set `LIVE_API_BASE_URL`
to point it at any already-running instance instead — Docker, Compose, or
the Kubernetes deployment all work the same way:

```bash
LIVE_API_BASE_URL=http://127.0.0.1:8000 uv run pytest test_live_api_integration.py -v
```

This project also includes a Dockerfile, a Docker Compose PostgreSQL stack,
Kubernetes manifests for a local `kind` cluster, and a GitHub Actions CI/CD
workflow (above) — none of them change the HTTP protocol or lifecycle in
`SPEC.md`. External brokers and an LLM remain outside its scope.
