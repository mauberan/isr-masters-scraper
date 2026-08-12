# utils/logging.py
#
# Structured JSON logging for the ISR pipeline.
# Replaces plain-text logging.basicConfig in pipeline.py.
#
# Why structured logging?
#   Plain text logs cannot be searched or filtered by production log
#   tools (Railway logs, Datadog, CloudWatch). JSON logs can.
#
# Twelve-factor principle: write to stdout only. Never to files.
# The platform handles collection and aggregation.
#
# Usage:
#   from utils.logging import setup_logging
#   setup_logging(level='INFO')

import logging
import json
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level':     record.levelname,
            'logger':    record.name,
            'message':   record.getMessage(),
        }
        if record.exc_info:
            log_obj['exception'] = self.formatException(record.exc_info)
        return json.dumps(log_obj, ensure_ascii=False)


def setup_logging(level: str = 'INFO') -> None:
    """
    Configure root logger with JSON output to stdout.
    Call once at application entry point.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)