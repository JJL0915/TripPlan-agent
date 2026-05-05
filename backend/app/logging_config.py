"""后端日志配置。"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


_RESERVED_LOG_RECORD_KEYS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


class ReadableLogFormatter(logging.Formatter):
    """输出适合本地终端阅读的一行日志，同时保留结构化字段。"""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        base = f"[{record.levelname}] {timestamp} {record.name} - {record.getMessage()}"

        fields: dict[str, Any] = {}
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_RECORD_KEYS or key.startswith("_"):
                continue
            if key == "taskName":
                continue
            fields[key] = self._json_safe(value)

        if fields:
            field_text = " ".join(f"{key}={self._format_value(value)}" for key, value in fields.items())
            base = f"{base} | {field_text}"

        if record.exc_info:
            base = f"{base}\n{self.formatException(record.exc_info)}"

        return base

    @staticmethod
    def _json_safe(value: Any) -> Any:
        try:
            json.dumps(value, ensure_ascii=False)
            return value
        except TypeError:
            return str(value)

    @staticmethod
    def _format_value(value: Any) -> str:
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, ensure_ascii=False, default=str)
        return str(value)


def setup_logging(level: str = "INFO") -> None:
    """初始化全局日志配置。"""
    root_logger = logging.getLogger()
    if getattr(root_logger, "_trip_agent_logging_configured", False):
        root_logger.setLevel(level.upper())
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ReadableLogFormatter())

    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())
    setattr(root_logger, "_trip_agent_logging_configured", True)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
