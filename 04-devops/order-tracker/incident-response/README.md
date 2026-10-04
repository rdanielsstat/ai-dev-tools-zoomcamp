# Incident responder

Receives Grafana alerts at `POST /alerts` (port 8001), saves the context needed to understand the problem, and starts the coding agent (Claude Code) in headless mode to investigate.

It runs on the host, not in Docker, because the agent needs your Claude Code login and the repository.

## Run it

You need `uv`, the `claude` CLI (logged in), and the observability stack from the parent directory running.

```bash
cd incident-response
uv run --frozen python responder.py
```

It listens on `127.0.0.1:8001`. Grafana in Docker can reach it at `http://host.docker.internal:8001/alerts`.

## What happens on an alert

For each firing alert (resolved ones are ignored), the responder creates `incidents/<time>-<alertname>/` with:

| File | Contents |
| --- | --- |
| `incident.md` | Summary: alert, endpoint, time range, dashboard link, requests, error logs, failing traces |
| `alert.json` | The alert as received and the parsed fields |
| `metrics.json` | Request counts by route and status in the time range (Prometheus) |
| `logs.json` | Warning and error logs with stack traces and trace IDs (Loki) |
| `traces.json` | Failing traces with all spans, attributes, and exception events (Tempo) |

The time range covers the alert's `time_window` annotation (15 minutes if missing) before it started, up to now. If a backend is down, the file records the error and the agent still starts.

Then it runs `claude -p` with [`prompt.md`](prompt.md) from the project root, in the background. The agent may read files, edit code, run the tests, and query the backends with `curl`. Everything else, including git commits, is denied. When it finishes, the incident directory also has:

| File | Contents |
| --- | --- |
| `response.md` | The agent's answer; the last line is `RESULT: TEST/FIXED/ESCALATE/NO_ACTION - ...` |
| `report.md` | The agent's incident report (real incidents only) |
| `status.json` | `running`, `done`, `failed`, or `timed_out`, with the last line of the answer |
| `agent-output.json`, `agent.log` | Raw agent output and stderr |

The responder also logs the last line, and you can read results over HTTP: `GET /incidents` lists incidents with their status and `GET /incidents/{id}` returns the summary and response. If the same alert and endpoint fire again while an agent is still working, the context is saved but no second agent starts.

## Settings

| Variable | Default |
| --- | --- |
| `RESPONDER_HOST`, `RESPONDER_PORT` | `127.0.0.1`, `8001` |
| `PROMETHEUS_URL`, `LOKI_URL`, `TEMPO_URL`, `GRAFANA_URL` | `http://localhost:9090`, `:3100`, `:3200`, `:3000` |
| `RESPONDER_AGENT_COMMAND` | `claude` |
| `RESPONDER_AGENT_MODEL` | the CLI's default |
| `RESPONDER_AGENT_TIMEOUT` | `1800` seconds |
| `RESPONDER_INCIDENTS_DIR` | `incident-response/incidents` (git-ignored) |

## Tests

```bash
uv run --frozen pytest -q
```

The tests use a fake agent (`tests/fake_agent.py`) and never call Claude.
