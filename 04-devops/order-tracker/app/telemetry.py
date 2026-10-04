import logging
import os

from opentelemetry import metrics, trace
from opentelemetry._logs import SeverityNumber, get_logger, set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    BatchLogRecordProcessor,
    ConsoleLogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)


SERVICE_NAME = "order-tracker"
METRIC_EXPORT_INTERVAL_MS = int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL", "5000"))
# Set to the Collector (e.g. http://otel-collector:4318) to export over OTLP; unset means console.
OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
SEVERITIES = {
    logging.DEBUG: SeverityNumber.DEBUG,
    logging.INFO: SeverityNumber.INFO,
    logging.WARNING: SeverityNumber.WARN,
    logging.ERROR: SeverityNumber.ERROR,
    logging.CRITICAL: SeverityNumber.FATAL,
}
# Standard LogRecord fields; anything else came from `extra=` and becomes an attribute.
RESERVED_RECORD_FIELDS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class OTelHandler(logging.Handler):
    """Forward stdlib log records to OpenTelemetry, keeping the active trace context."""

    def __init__(self, logger_provider):
        super().__init__()
        self._logger = get_logger(SERVICE_NAME, logger_provider=logger_provider)

    def emit(self, record):
        attributes = {
            key: value for key, value in vars(record).items()
            if key not in RESERVED_RECORD_FIELDS
        }
        attributes["code.function"] = record.funcName
        self._logger.emit(
            timestamp=int(record.created * 1e9),
            severity_number=SEVERITIES.get(record.levelno, SeverityNumber.UNSPECIFIED),
            severity_text=record.levelname,
            body=record.getMessage(),
            attributes=attributes,
            exception=record.exc_info[1] if record.exc_info else None,
        )


def otlp_pipeline():
    """Batch everything to the Collector over OTLP/HTTP; the exporters read OTEL_EXPORTER_OTLP_*."""
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    return (
        BatchSpanProcessor(OTLPSpanExporter()),
        OTLPMetricExporter(),
        BatchLogRecordProcessor(OTLPLogExporter()),
    )


def console_pipeline():
    """Print everything to stdout so `docker compose logs app` shows it."""
    return (
        SimpleSpanProcessor(ConsoleSpanExporter()),
        ConsoleMetricExporter(),
        SimpleLogRecordProcessor(ConsoleLogRecordExporter()),
    )


def setup_telemetry():
    resource = Resource.create({"service.name": SERVICE_NAME})
    span_processor, metric_exporter, log_processor = (
        otlp_pipeline() if OTLP_ENDPOINT else console_pipeline()
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(span_processor)
    trace.set_tracer_provider(tracer_provider)

    reader = PeriodicExportingMetricReader(
        metric_exporter, export_interval_millis=METRIC_EXPORT_INTERVAL_MS
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(log_processor)
    set_logger_provider(logger_provider)

    app_logger = logging.getLogger("order_tracker")
    app_logger.setLevel(logging.INFO)
    app_logger.addHandler(OTelHandler(logger_provider))


setup_telemetry()

tracer = trace.get_tracer(SERVICE_NAME)
meter = metrics.get_meter(SERVICE_NAME)
logger = logging.getLogger("order_tracker")

request_counter = meter.create_counter(
    "http.server.requests",
    unit="{request}",
    description="HTTP requests handled, by route and status code",
)# FastAPI already records http.server.request.duration and a server span per request.
