import logging
import re


def redact_sensitive(log_message):
    """
    Removes Base64 cryptographic keys and UUID strings from log output.
    """
    if not isinstance(log_message, str):
        return log_message
    # Redact standard UUID structures
    log_message = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "[REDACTED-UUID]",
        log_message,
    )
    # Redact Base64 ciphertext/key payloads
    log_message = re.sub(r"[A-Za-z0-9+/]{20,}={0,2}", "[REDACTED-B64]", log_message)
    return log_message


class RedactingFilter(logging.Filter):
    """Logging filter to invoke redaction on all processed logs."""

    def filter(self, record):
        if record.msg and isinstance(record.msg, str):
            record.msg = redact_sensitive(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                new_args = {}
                for k, v in record.args.items():
                    if isinstance(v, str):
                        new_args[k] = redact_sensitive(v)
                    else:
                        new_args[k] = v
                record.args = new_args
            elif isinstance(record.args, (list, tuple)):
                new_args = []
                for v in record.args:
                    if isinstance(v, str):
                        new_args.append(redact_sensitive(v))
                    else:
                        new_args.append(v)
                record.args = (
                    tuple(new_args) if isinstance(record.args, tuple) else new_args
                )
        return True


import builtins

_original_print = builtins.print


def setup_logging(app=None):
    """Registers the RedactingFilter onto root and Flask loggers."""
    redactor = RedactingFilter()
    logging.getLogger().addFilter(redactor)
    if app:
        app.logger.addFilter(redactor)

    def secured_print(*args, **kwargs):
        msg = " ".join(str(arg) for arg in args)
        _original_print(redact_sensitive(msg), **kwargs)

    builtins.print = secured_print
