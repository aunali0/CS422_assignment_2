import json
from typing import Literal

LOG_PREFIX_WIDTH = 9
LogMsgType = Literal["control", "data", "test", "error"]


def log_message(msg_type: LogMsgType, msg: str) -> None:
    print(f"{f'[{msg_type}]':<{LOG_PREFIX_WIDTH}} {msg}")


def log_json(msg_type: LogMsgType, action: str, payload: object) -> None:
    log_message(msg_type, f"{action} JSON:")
    json_fmt = json.dumps(payload, indent=2, ensure_ascii=False)

    for line in json_fmt.splitlines():
        print(f"{'':{LOG_PREFIX_WIDTH}} {line}")


def log_test_progress(bytes_sent: int, time_passed: float, duration: int) -> None:
    log_message(
        "test", f"{time_passed:.1f}s / {duration}s | {bytes_sent / (1024 * 1024):.2f} MiB sent"
    )
