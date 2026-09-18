"""Guards against the implementation drifting from ../openapi.yaml, the
contract this backend was built against."""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

SPEC_PATH = Path(__file__).resolve().parent.parent.parent / "openapi.yaml"

_PARAM = re.compile(r"\{[^}]+\}")


def _normalize(path: str) -> str:
    """Path parameter names are just labels (openapi.yaml says {groupId},
    FastAPI's schema says {group_id} after the Python parameter name) — only
    the segment shape has to match."""
    return _PARAM.sub("{}", path)


def _spec_paths() -> dict[str, set[str]]:
    with SPEC_PATH.open() as f:
        spec = yaml.safe_load(f)
    out: dict[str, set[str]] = {}
    for path, methods in spec["paths"].items():
        # openapi.yaml paths are already server-relative (server url is /api)
        out[_normalize(path)] = {m.upper() for m in methods if m in ("get", "post", "patch", "put", "delete")}
    return out


def test_every_documented_endpoint_exists_in_the_app(client: TestClient) -> None:
    app_schema = client.get("/openapi.json").json()
    app_paths: dict[str, set[str]] = {}
    for path, methods in app_schema["paths"].items():
        # the app mounts routers under /api; strip that to compare against the spec
        assert path.startswith("/api")
        app_paths[_normalize(path[len("/api") :])] = {m.upper() for m in methods}

    for path, methods in _spec_paths().items():
        assert path in app_paths, f"{path} documented in openapi.yaml but missing from the app"
        missing = methods - app_paths[path]
        assert not missing, f"{path} missing methods {missing}"


def test_openapi_yaml_is_valid() -> None:
    from openapi_spec_validator import validate

    with SPEC_PATH.open() as f:
        spec = yaml.safe_load(f)
    validate(spec)  # raises if invalid
