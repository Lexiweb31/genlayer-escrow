"""Safe structured operational telemetry for the trusted Merit backend."""
from __future__ import annotations

import json
import logging
import re
from typing import Any


LOGGER = logging.getLogger("merit.telemetry")
_SAFE_FIELDS = frozenset({
    "action",
    "duration_ms",
    "error_code",
    "job",
    "kind",
    "method",
    "network",
    "outcome",
    "path",
    "role",
    "status",
    "status_code",
    "tx_hash",
})
_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_.:/-]{1,160}$")


def _safe_value(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = str(value)
    return text if _CODE_PATTERN.fullmatch(text) else "redacted"


def log_event(name: str, **fields: Any) -> None:
    """Write a JSON event after dropping fields that could contain secrets."""
    event = _safe_value(name)
    payload: dict[str, str | int | float | bool | None] = {
        "event": event if isinstance(event, str) else "redacted",
    }
    payload.update({
        key: _safe_value(value)
        for key, value in fields.items()
        if key in _SAFE_FIELDS
    })
    level = logging.WARNING if "error" in payload["event"] or "failure" in payload["event"] else logging.INFO
    LOGGER.log(level, json.dumps(payload, separators=(",", ":"), sort_keys=True))
