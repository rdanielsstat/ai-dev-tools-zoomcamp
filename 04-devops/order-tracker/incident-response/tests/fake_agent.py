"""Stands in for `claude -p ... --output-format json` in tests."""
import json
import os
import sys
import time

time.sleep(float(os.getenv("FAKE_AGENT_SLEEP", "0")))
prompt = sys.argv[sys.argv.index("-p") + 1]
print(json.dumps({
    "result": f"Got a prompt of {len(prompt)} characters.\nRESULT: TEST - fake agent ran.",
    "is_error": False,
    "total_cost_usd": 0,
}))
