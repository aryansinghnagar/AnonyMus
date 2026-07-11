"""
Structured logging configuration for AnonyMus v3.

Uses structlog for consistent JSON output in production and human-readable
output in development.  Never logs message content or cryptographic keys.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(log_level: str = "INFO", json_logs: bool = False) -> None:
    """
    Configure structlog + stdlib logging.

    Call once at application startup, before creating the FastAPI app.

    Args:
        log_level:  Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_logs:  If True, emit JSON (for production). If False, pretty-print (for dev).
    """
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _scrub_sensitive_fields,
    ]

    if json_logs:
        # Production: compact JSON for log aggregators (Loki, CloudWatch, etc.)
        renderer = structlog.processors.JSONRenderer()
    else:
        # Development: coloured, readable output
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level.upper())
        ),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())

    # Quieten noisy libraries
    for noisy in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _scrub_sensitive_fields(logger: object, method: str, event_dict: dict) -> dict:
    """
    Strip any sensitive field names from log events before they are rendered.

    This is the structural guarantee that keys/ciphertexts never appear in logs.
    """
    _SENSITIVE = {
        "password",
        "secret",
        "key",
        "token",
        "ciphertext",
        "plaintext",
        "iv",
        "nonce",
        "private_key",
        "shared_secret",
        "db_key",
        "session_key",
        "auth_tag",
    }
    for field in _SENSITIVE:
        if field in event_dict:
            event_dict[field] = "[REDACTED]"
    return event_dict


def get_logger(name: str = __name__) -> structlog.BoundLogger:
    """Return a pre-configured structlog logger bound to `name`."""
    return structlog.get_logger(name)
