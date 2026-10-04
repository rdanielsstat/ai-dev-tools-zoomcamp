# Order Tracker

A small order tracking app for the AI Dev Tools Zoomcamp observability homework. It includes a web page, API, tests, and a Docker Compose setup. You add telemetry, alerts, and an incident responder in Homework 4.

The main user flow is creating an order and checking its status. Three sample orders are created on first startup.

## Run it

You need Docker with Compose. To run the tests, you also need Python 3.11+ and `uv`.

```bash
docker compose up --build -d --wait
```

Open <http://127.0.0.1:8000>. The API is at `/api/orders`, and the health check is at `/healthz`. Data is stored in a Docker volume and survives container recreation.

If port 8000 is occupied, set `ORDER_TRACKER_PORT`, for example:

```bash
ORDER_TRACKER_PORT=18080 docker compose up --build -d --wait
```

Run tests with `uv run --frozen pytest -q`. Stop the app with `docker compose down`. Add `-v` only if you also want to delete the order data.

## Observability

The app sends OpenTelemetry metrics, logs, and traces over OTLP to an OpenTelemetry Collector, which forwards them to Prometheus (metrics), Loki (logs), and Tempo (traces). Grafana has all three as data sources and opens on the provisioned **Order Tracker** dashboard (request counts, 4xx/5xx errors, logs, and order lookup traces). The configuration lives in `observability/`.

| Service | URL |
| --- | --- |
| Grafana (no login) | <http://127.0.0.1:3000> |
| Prometheus | <http://127.0.0.1:9090> |
| Loki | <http://127.0.0.1:3100> |
| Tempo | <http://127.0.0.1:3200> |

Override the ports with `GRAFANA_PORT`, `PROMETHEUS_PORT`, `LOKI_PORT`, and `TEMPO_PORT`. The request counter is `http_server_requests_total` in Prometheus, labelled with `http_route` and `http_response_status_code`. In Grafana, a log line links to its trace, and a span links back to its logs. Tempo search leaves out the last 30 seconds, so a brand-new trace takes a moment to show up.

The Grafana alert rule **Order Tracker 5xx responses** (folder *Order Tracker*, provisioned from `observability/grafana/provisioning/alerting/`) checks every 10 seconds for 5xx responses per endpoint over the last 5 minutes. It fires as soon as one appears and returns to Normal once 5 minutes pass without any. "No data" (no 5xx has happened yet) counts as Normal. Each alert has the endpoint, time window, and a dashboard link. No contact point is set up yet.

`incident-response/` has a service that receives these alerts, saves the related metrics, logs, and traces, and starts a coding agent to investigate. See [its README](incident-response/README.md).

Without `OTEL_EXPORTER_OTLP_ENDPOINT` (for example when running `uvicorn` locally), the app prints telemetry to the console instead.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Web page |
| GET | `/healthz` | Database health check |
| GET | `/api/orders` | List orders |
| POST | `/api/orders` | Create an order |
| GET | `/api/orders/{id}` | Check an order |
| PATCH | `/api/orders/{id}` | Change an order status |

The app uses SQLite to keep setup small. Run one app container at a time. The course exercise is about detecting and handling an incident, not scaling the database.
