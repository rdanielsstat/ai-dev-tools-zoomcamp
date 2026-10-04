import os

# Telemetry exporters would write to stdout after pytest closes it.
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
