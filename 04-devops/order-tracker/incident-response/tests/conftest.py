import os
import shlex
import sys
from pathlib import Path

# Never start the real agent or reach a real backend from tests.
os.environ["RESPONDER_AGENT_COMMAND"] = shlex.join([sys.executable, str(Path(__file__).parent / "fake_agent.py")])
for name in ("PROMETHEUS_URL", "LOKI_URL", "TEMPO_URL"):
    os.environ[name] = "http://127.0.0.1:9"
