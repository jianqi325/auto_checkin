from __future__ import annotations

import logging
import re
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_SENSITIVE_PATTERNS = [
    re.compile(r"(password\s*[=:]\s*)([^\s,;]+)", re.IGNORECASE),
    re.compile(r"(cookie\s*[=:]\s*)([^\s,;]+)", re.IGNORECASE),
]


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = record.getMessage()
            for pattern in _SENSITIVE_PATTERNS:
                msg = pattern.sub(r"\1***", msg)
            record.msg = msg
            record.args = ()
        return True


class ContextAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.setdefault("extra", {})
        for key, value in self.extra.items():
            extra.setdefault(key, value)
        return msg, kwargs


def setup_logging(log_file: Path, retention_days: int) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("auto_checkin")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [run_id=%(run_id)s] [site=%(site)s] [trigger=%(trigger)s] %(message)s"
    )

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    stream.addFilter(RedactFilter())
    logger.addHandler(stream)

    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        backupCount=max(1, retention_days),
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.addFilter(RedactFilter())
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger


def with_context(logger: logging.Logger, run_id: str, site: str, trigger: str) -> ContextAdapter:
    return ContextAdapter(logger, {"run_id": run_id, "site": site, "trigger": trigger})
