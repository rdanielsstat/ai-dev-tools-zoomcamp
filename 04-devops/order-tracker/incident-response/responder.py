"""Incident responder: receives Grafana alerts, saves their context, and starts a headless agent.

For each firing alert it creates incidents/<id>/ with the alert, the affected endpoint, request
metrics, error logs, and traces from the observability stack, then runs the coding agent on it.
"""

import json
import logging
import os
import re
import shlex
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse


HERE = Path(__file__).resolve().parent
PROJECT_DIR = Path(os.getenv("RESPONDER_PROJECT_DIR", HERE.parent)).resolve()
INCIDENTS_DIR = Path(os.getenv("RESPONDER_INCIDENTS_DIR", HERE / "incidents")).resolve()
PROMPT_FILE = HERE / "prompt.md"

SERVICE_NAME = os.getenv("RESPONDER_SERVICE_NAME", "order-tracker")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
LOKI_URL = os.getenv("LOKI_URL", "http://localhost:3100")
TEMPO_URL = os.getenv("TEMPO_URL", "http://localhost:3200")
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3000")

AGENT_COMMAND = shlex.split(os.getenv("RESPONDER_AGENT_COMMAND", "claude"))
AGENT_MODEL = os.getenv("RESPONDER_AGENT_MODEL")
AGENT_TIMEOUT_S = int(os.getenv("RESPONDER_AGENT_TIMEOUT", "1800"))
# Headless runs cannot answer permission prompts: edits are allowed, and anything else not
# listed here is denied.
AGENT_ALLOWED_TOOLS = [
    "Read", "Grep", "Glob", "Edit", "Write",
    "Bash(uv run --frozen pytest:*)",
    "Bash(curl -s http://localhost:*)",
    "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)",
]

DEFAULT_WINDOW_MINUTES = 15
QUERY_TIMEOUT_S = 10
MAX_LOGS = 100
MAX_TRACES = 10

log = logging.getLogger("incident_response")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="Incident Responder")
_running = {}  # alert key -> incident id, for agents still working
_running_lock = threading.Lock()


# --- Alert parsing ---------------------------------------------------------------------------

def parse_time(value):
    """Parse Grafana's RFC 3339 timestamps (which may carry nanoseconds); None if unset."""
    if not value or value.startswith("0001-"):
        return None
    value = re.sub(r"(\.\d{6})\d+", r"\1", value.replace("Z", "+00:00"))
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def parse_duration(value):
    match = re.fullmatch(r"\s*(\d+)\s*([smhd])\s*", value or "")
    if not match:
        return None
    unit = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}[match[2]]
    return timedelta(**{unit: int(match[1])})


def describe(alert, now):
    """The facts an investigator needs first: what fired, where, and over which time range."""
    labels = alert.get("labels") or {}
    annotations = alert.get("annotations") or {}
    method, route = labels.get("http_request_method"), labels.get("http_route")
    endpoint = (
        labels.get("endpoint")
        or annotations.get("endpoint")
        or " ".join(part for part in (method, route) if part)
        or None
    )
    window = parse_duration(annotations.get("time_window"))
    window_text = annotations.get("time_window") if window else f"{DEFAULT_WINDOW_MINUTES}m"
    window = window or timedelta(minutes=DEFAULT_WINDOW_MINUTES)
    starts_at = parse_time(alert.get("startsAt")) or now
    return {
        "alertname": labels.get("alertname", "unknown"),
        "status": alert.get("status", "firing"),
        "is_test": labels.get("test") == "true",
        "summary": annotations.get("summary"),
        "description": annotations.get("description"),
        "endpoint": endpoint,
        "http_route": route,
        "time_window": window_text,
        "from": (min(starts_at, now) - window).isoformat(),
        "to": now.isoformat(),
        "starts_at": alert.get("startsAt"),
        "dashboard_url": alert.get("dashboardURL") or annotations.get("dashboard_url"),
        "panel_url": alert.get("panelURL"),
        "generator_url": alert.get("generatorURL"),
        "labels": labels,
        "annotations": annotations,
        "values": alert.get("values"),
    }


def alert_key(info):
    return f"{info['alertname']}|{info['endpoint'] or ''}"


# --- Context collection ----------------------------------------------------------------------

def get_json(base, path, params=None):
    url = f"{base}{path}" + (f"?{urlencode(params)}" if params else "")
    with urlopen(url, timeout=QUERY_TIMEOUT_S) as response:
        return json.load(response)


def collect(name, fn):
    """Run one collector; a down backend is recorded in the file instead of failing the alert."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - any failure here is context, not a crash
        log.warning("Could not collect %s: %s", name, exc)
        return {"error": f"{type(exc).__name__}: {exc}"}


def collect_metrics(info, start, end):
    seconds = max(int((end - start).total_seconds()), 60)
    query = (
        "sum by (http_request_method, http_route, http_response_status_code) "
        f'(increase(http_server_requests_total{{job="{SERVICE_NAME}"}}[{seconds}s]))'
    )
    data = get_json(PROMETHEUS_URL, "/api/v1/query", {"query": query, "time": end.timestamp()})
    rows = [
        {**row["metric"], "requests": round(float(row["value"][1]), 2)}
        for row in data["data"]["result"]
        if row["metric"].get("http_route") != "/healthz"
    ]
    rows.sort(key=lambda row: row["requests"], reverse=True)
    return {"query": query, "window": f"{seconds}s", "requests_by_route_and_status": rows}


def collect_logs(info, start, end):
    query = f'{{service_name="{SERVICE_NAME}"}} | severity_text=~"WARN.*|ERROR|CRITICAL|FATAL"'
    data = get_json(LOKI_URL, "/loki/api/v1/query_range", {
        "query": query,
        "start": int(start.timestamp() * 1e9),
        "end": int(end.timestamp() * 1e9),
        "limit": MAX_LOGS,
        "direction": "backward",
    })
    entries = []
    for stream in data["data"]["result"]:
        labels = stream["stream"]
        for timestamp, line in stream["values"]:
            entries.append({
                "time": datetime.fromtimestamp(int(timestamp) / 1e9, timezone.utc).isoformat(),
                "level": labels.get("severity_text") or labels.get("detected_level"),
                "message": line,
                "trace_id": labels.get("trace_id"),
                "attributes": {k: v for k, v in labels.items() if k not in {"severity_text", "trace_id"}},
            })
    entries.sort(key=lambda entry: entry["time"], reverse=True)
    return {"query": query, "count": len(entries), "entries": entries}


def otlp_value(value):
    for kind in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if kind in value:
            return value[kind]
    if "arrayValue" in value:
        return [otlp_value(v) for v in value["arrayValue"].get("values", [])]
    return value


def otlp_attributes(attributes):
    return {item["key"]: otlp_value(item.get("value", {})) for item in attributes or []}


def simplify_trace(trace_id, data):
    """Flatten Tempo's OTLP JSON into a readable span list with errors and exceptions."""
    spans = []
    for batch in data.get("batches") or data.get("resourceSpans") or []:
        service = otlp_attributes(batch.get("resource", {}).get("attributes")).get("service.name")
        for scope in batch.get("scopeSpans", []):
            for span in scope.get("spans", []):
                start_ns, end_ns = int(span["startTimeUnixNano"]), int(span["endTimeUnixNano"])
                spans.append({
                    "name": span["name"],
                    "service": service,
                    "span_id": span.get("spanId"),
                    "parent_span_id": span.get("parentSpanId"),
                    "start": datetime.fromtimestamp(start_ns / 1e9, timezone.utc).isoformat(),
                    "duration_ms": round((end_ns - start_ns) / 1e6, 3),
                    "status": span.get("status", {}),
                    "attributes": otlp_attributes(span.get("attributes")),
                    "events": [
                        {"name": event["name"], "attributes": otlp_attributes(event.get("attributes"))}
                        for event in span.get("events", [])
                    ],
                })
    spans.sort(key=lambda span: span["start"])
    return {"trace_id": trace_id, "spans": spans}


def collect_traces(info, start, end, log_trace_ids):
    conditions = [f'resource.service.name="{SERVICE_NAME}"', "span.http.response.status_code>=500"]
    if info["http_route"]:
        conditions.append(f'span.http.route="{info["http_route"]}"')
    query = "{" + " && ".join(conditions) + "}"
    search = get_json(TEMPO_URL, "/api/search", {
        "q": query,
        "start": int(start.timestamp()),
        "end": int(end.timestamp()) + 1,
        "limit": MAX_TRACES,
    })
    trace_ids = [trace["traceID"] for trace in search.get("traces", [])]
    # Traces referenced by error logs are relevant even if search has not indexed them yet.
    for trace_id in log_trace_ids:
        if trace_id not in trace_ids:
            trace_ids.append(trace_id)
    traces = []
    for trace_id in trace_ids[:MAX_TRACES]:
        trace = collect(f"trace {trace_id}", lambda: get_json(TEMPO_URL, f"/api/traces/{quote(trace_id)}"))
        traces.append(trace if "error" in trace else simplify_trace(trace_id, trace))
    return {"query": query, "count": len(traces), "traces": traces}


def gather_context(info):
    start, end = datetime.fromisoformat(info["from"]), datetime.fromisoformat(info["to"])
    metrics = collect("metrics", lambda: collect_metrics(info, start, end))
    logs = collect("logs", lambda: collect_logs(info, start, end))
    log_trace_ids = list(dict.fromkeys(
        entry["trace_id"] for entry in logs.get("entries", [])
        if entry.get("trace_id") and entry.get("level") in ("ERROR", "CRITICAL", "FATAL")
    ))
    traces = collect("traces", lambda: collect_traces(info, start, end, log_trace_ids))
    return metrics, logs, traces


# --- Incident files --------------------------------------------------------------------------

def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, default=str) + "\n")


def summary_markdown(incident_id, info, metrics, logs, traces):
    lines = [
        f"# Incident {incident_id}",
        "",
        f"- **Alert:** {info['alertname']} ({info['status']})" + (" — TEST ALERT" if info["is_test"] else ""),
        f"- **Summary:** {info['summary'] or '-'}",
        f"- **Description:** {info['description'] or '-'}",
        f"- **Endpoint:** {info['endpoint'] or 'not given'}",
        f"- **Time range investigated:** {info['from']} to {info['to']} (alert window {info['time_window']})",
        f"- **Dashboard:** {info['dashboard_url'] or GRAFANA_URL + '/d/order-tracker'}",
        "",
        "## Requests in the time range",
        "",
    ]
    if "error" in metrics:
        lines.append(f"Could not query Prometheus: {metrics['error']}")
    elif not metrics["requests_by_route_and_status"]:
        lines.append("No requests recorded.")
    else:
        lines += ["| Method | Route | Status | Requests (approx.) |", "| --- | --- | --- | --- |"]
        lines += [
            f"| {r.get('http_request_method')} | {r.get('http_route')} | "
            f"{r.get('http_response_status_code')} | {r['requests']} |"
            for r in metrics["requests_by_route_and_status"]
        ]
    lines += ["", "## Warning and error logs", ""]
    if "error" in logs:
        lines.append(f"Could not query Loki: {logs['error']}")
    elif not logs["entries"]:
        lines.append("None.")
    else:
        lines += [
            f"- {e['time']} {e['level']} {e['message']} (trace {e['trace_id'] or '-'})"
            for e in logs["entries"][:20]
        ]
    lines += ["", "## Traces", ""]
    if "error" in traces:
        lines.append(f"Could not query Tempo: {traces['error']}")
    elif not traces["traces"]:
        lines.append("None found.")
    else:
        for trace in traces["traces"]:
            errors = [
                span["name"] for span in trace.get("spans", [])
                if span["status"].get("code") in ("STATUS_CODE_ERROR", 2)
            ]
            lines.append(f"- {trace['trace_id']}: error spans {', '.join(errors) or 'none'}")
    lines += [
        "",
        "## Files",
        "",
        "- `alert.json`: the alert as received from Grafana, plus the parsed fields",
        "- `metrics.json`: request counts by route and status (Prometheus)",
        "- `logs.json`: warning and error logs, with exception stack traces and trace IDs (Loki)",
        "- `traces.json`: failing traces with every span, attribute, and exception event (Tempo)",
        "",
    ]
    return "\n".join(lines)


def create_incident(alert, now):
    info = describe(alert, now)
    slug = re.sub(r"[^a-z0-9]+", "-", info["alertname"].lower()).strip("-") or "alert"
    incident_id = f"{now:%Y%m%dT%H%M%S%fZ}-{slug}"
    incident_dir = INCIDENTS_DIR / incident_id
    incident_dir.mkdir(parents=True)

    metrics, logs, traces = gather_context(info)
    write_json(incident_dir / "alert.json", {"parsed": info, "raw": alert})
    write_json(incident_dir / "metrics.json", metrics)
    write_json(incident_dir / "logs.json", logs)
    write_json(incident_dir / "traces.json", traces)
    (incident_dir / "incident.md").write_text(summary_markdown(incident_id, info, metrics, logs, traces))
    write_json(incident_dir / "status.json", {"agent": "pending"})
    return incident_id, incident_dir, info


# --- Agent -----------------------------------------------------------------------------------

def agent_prompt(incident_dir):
    # Plain replacement, not str.format: the prompt contains literal braces (routes, TraceQL).
    prompt = PROMPT_FILE.read_text()
    for name, value in {
        "incident_dir": incident_dir,
        "project_dir": PROJECT_DIR,
        "prometheus_url": PROMETHEUS_URL,
        "loki_url": LOKI_URL,
        "tempo_url": TEMPO_URL,
    }.items():
        prompt = prompt.replace("{{" + name + "}}", str(value))
    return prompt


def agent_command(incident_dir):
    command = [
        *AGENT_COMMAND,
        "-p", agent_prompt(incident_dir),
        "--output-format", "json",
        "--permission-mode", "acceptEdits",
        "--allowedTools", *AGENT_ALLOWED_TOOLS,
    ]
    if AGENT_MODEL:
        command += ["--model", AGENT_MODEL]
    return command


def agent_env():
    # The responder may itself be started from a Claude Code session; give the agent a clean one.
    return {k: v for k, v in os.environ.items() if k not in {"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"}}


def run_agent(key, incident_id, incident_dir):
    status = {"agent": "running", "command": AGENT_COMMAND[0],
              "started_at": datetime.now(timezone.utc).isoformat()}
    write_json(incident_dir / "status.json", status)
    log.info("Agent started for incident %s", incident_id)
    try:
        with open(incident_dir / "agent-output.json", "w") as stdout, \
                open(incident_dir / "agent.log", "w") as stderr:
            result = subprocess.run(
                agent_command(incident_dir), cwd=PROJECT_DIR, env=agent_env(),
                stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                timeout=AGENT_TIMEOUT_S,
            )
        status["exit_code"] = result.returncode
        raw = (incident_dir / "agent-output.json").read_text()
        try:
            output = json.loads(raw)
            response = output.get("result") or ""
            status["agent"] = "failed" if output.get("is_error") or result.returncode else "done"
            status["cost_usd"] = output.get("total_cost_usd")
        except json.JSONDecodeError:
            response = raw
            status["agent"] = "done" if result.returncode == 0 else "failed"
        (incident_dir / "response.md").write_text(response.rstrip() + "\n")
        last_lines = [line for line in response.strip().splitlines() if line.strip()]
        status["last_line"] = last_lines[-1] if last_lines else None
    except subprocess.TimeoutExpired:
        status.update(agent="timed_out", error=f"Agent ran longer than {AGENT_TIMEOUT_S}s")
    except Exception as exc:  # noqa: BLE001 - report any launch failure in status.json
        status.update(agent="failed", error=f"{type(exc).__name__}: {exc}")
    finally:
        status["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(incident_dir / "status.json", status)
        with _running_lock:
            _running.pop(key, None)
        log.info("Agent %s for incident %s: %s", status["agent"], incident_id,
                 status.get("last_line") or status.get("error"))


# --- HTTP API --------------------------------------------------------------------------------

@app.get("/healthz")
def health():
    return {"status": "ok"}


@app.post("/alerts", status_code=202)
def receive_alerts(payload: dict):
    """Grafana webhook contact point. Starts one agent per firing alert, unless one is already
    investigating the same alert and endpoint (Grafana re-sends firing alerts)."""
    now = datetime.now(timezone.utc)
    results, ignored = [], 0
    for alert in payload.get("alerts") or []:
        if alert.get("status", "firing") != "firing":
            ignored += 1
            continue
        incident_id, incident_dir, info = create_incident(alert, now)
        key = alert_key(info)
        with _running_lock:
            already = _running.get(key)
            if not already:
                _running[key] = incident_id
        if already:
            write_json(incident_dir / "status.json", {"agent": "skipped", "investigated_by": already})
            agent = f"already running for incident {already}"
        else:
            threading.Thread(target=run_agent, args=(key, incident_id, incident_dir), daemon=True).start()
            agent = "started"
        log.info("Incident %s (%s, endpoint %s): agent %s", incident_id, info["alertname"],
                 info["endpoint"], agent)
        results.append({"incident": incident_id, "dir": str(incident_dir), "agent": agent})
    if not results and not ignored:
        return JSONResponse({"error": "payload has no alerts"}, status_code=400)
    return {"incidents": results, "ignored_resolved": ignored}


def read_incident(incident_dir):
    status_file = incident_dir / "status.json"
    status = json.loads(status_file.read_text()) if status_file.exists() else {}
    return {"incident": incident_dir.name, **status}


@app.get("/incidents")
def list_incidents():
    if not INCIDENTS_DIR.exists():
        return []
    return [read_incident(d) for d in sorted(INCIDENTS_DIR.iterdir(), reverse=True) if d.is_dir()]


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str):
    incident_dir = INCIDENTS_DIR / incident_id
    if not re.fullmatch(r"[0-9A-Za-z][\w-]*", incident_id) or not incident_dir.is_dir():
        raise HTTPException(404, "Incident not found")
    response_file = incident_dir / "response.md"
    return {
        **read_incident(incident_dir),
        "summary": (incident_dir / "incident.md").read_text(),
        "response": response_file.read_text() if response_file.exists() else None,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("RESPONDER_HOST", "127.0.0.1"),
                port=int(os.getenv("RESPONDER_PORT", "8001")))
