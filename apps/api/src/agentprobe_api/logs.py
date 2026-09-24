"""Structured JSON logging, request IDs and secret redaction.

RedactFilter sits on the handler, so every record that reaches output is scrubbed, whether
it comes from our code, uvicorn, SQLAlchemy or a library traceback.
"""

import json
import logging
import re
import sys
from contextvars import ContextVar
from typing import IO, Any
from urllib.parse import parse_qsl, urlencode

REDACTED = "[REDACTED]"
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Field names whose values are always secret.
_SENSITIVE_NAME = re.compile(r"secret|token|key|password|authorization|cookie", re.IGNORECASE)
# Secret-looking values anywhere in free text (messages, tracebacks, reprs).
_SENSITIVE_VALUE = [
    (re.compile(r"\bap_[A-Za-z0-9_\-]{8,}"), REDACTED),  # API keys
    (re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+"), REDACTED),  # JWTs
    (re.compile(r"(?i)\b(bearer|basic)\s+[^\s'\",]+"), r"\1 " + REDACTED),
    # key=value / "key": "value" pairs whose name looks sensitive
    (
        re.compile(
            r"(?i)([\"']?[\w-]*(?:secret|token|key|password|authorization|cookie)[\w-]*[\"']?"
            r"\s*[=:]\s*)([\"']?)[^\s&,;\"'}]+"
        ),
        r"\1\2" + REDACTED,
    ),
]
_STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "request_id"}


def scrub_text(text: str) -> str:
    for pattern, replacement in _SENSITIVE_VALUE:
        text = pattern.sub(replacement, text)
    return text


def redact(value: Any, name: str = "") -> Any:
    if name and _SENSITIVE_NAME.search(name):
        return REDACTED
    if isinstance(value, dict):
        return {k: redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return scrub_text(value)
    return value


def redact_query(query: str) -> str:
    pairs = parse_qsl(query, keep_blank_values=True)
    return urlencode([(k, REDACTED if _SENSITIVE_NAME.search(k) else v) for k, v in pairs])


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = scrub_text(record.getMessage())
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = scrub_text(record.exc_text)
        record.exc_info = None  # formatted and scrubbed above; don't let a formatter redo it
        for attr in set(vars(record)) - _STANDARD_ATTRS:
            setattr(record, attr, redact(getattr(record, attr), attr))
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        entry.update({k: v for k, v in vars(record).items() if k not in _STANDARD_ATTRS})
        if record.exc_text:
            entry["exc"] = record.exc_text
        return json.dumps(entry, default=str)


def configure_logging(level: str = "INFO", stream: IO[str] | None = None) -> logging.Handler:
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.addFilter(RedactFilter())
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    for old in [h for h in root.handlers if any(isinstance(f, RedactFilter) for f in h.filters)]:
        root.removeHandler(old)  # idempotent: reconfiguring replaces our handler
    root.addHandler(handler)
    root.setLevel(level)
    # Our access line replaces uvicorn's, which would log raw query strings (stream tokens).
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True
    return handler
