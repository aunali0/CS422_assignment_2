import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

LogLevel = Literal["control", "data", "test", "error", "destinations"]
logger = logging.getLogger(__name__)

LOG_LEVELS: dict[LogLevel, int] = {
    "control": logging.DEBUG,
    "data": logging.DEBUG,
    "test": logging.INFO,
    "error": logging.ERROR,
    "destinations": logging.INFO,
}


@contextmanager
def suppress_logging() -> Iterator[None]:
    was_disabled = logger.disabled
    logger.disabled = True

    try:
        yield
    finally:
        logger.disabled = was_disabled


def log_message(level: LogLevel, msg: str) -> None:
    logger.log(LOG_LEVELS[level], "[%s] %s", level, msg)


def log_json(level: LogLevel, action: str, payload: object) -> None:
    if not logger.isEnabledFor(LOG_LEVELS[level]):
        return

    payload_str = json.dumps(payload, indent=2, ensure_ascii=False)
    indent = " " * len(f"[{level}] ")
    indented_json = "\n".join(f"{indent}{line}" for line in payload_str.splitlines())
    log_message(level, f"{action} JSON:\n{indented_json}")


def log_test_progress(bytes_sent: int, time_passed: float, duration: int) -> None:
    log_message(
        "test", f"{time_passed:.1f}s / {duration}s | {bytes_sent / (1024 * 1024):.1f} MiB sent"
    )
