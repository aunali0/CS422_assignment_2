import json
import secrets
import socket
from enum import IntEnum
from string import ascii_lowercase
from typing import Literal


from pydantic import BaseModel, ConfigDict, Field

from log_utils import LogLevel, log_json, log_message


class State(IntEnum):
    SERVER_ERROR = -2
    ACCESS_DENIED = -1
    TEST_START = 1
    TEST_RUNNING = 2
    TEST_END = 4
    PARAM_EXCHANGE = 9
    CREATE_STREAMS = 10
    SERVER_TERMINATE = 11
    CLIENT_TERMINATE = 12
    EXCHANGE_RESULTS = 13
    DISPLAY_RESULTS = 14
    IPERF_START = 15
    IPERF_DONE = 16


class IPerf3Stream(BaseModel):
    model_config = ConfigDict(strict=True, allow_inf_nan=False)

    id: Literal[1]
    bytes: int = Field(ge=0)
    retransmits: int
    jitter: float = Field(ge=0)
    errors: int = Field(ge=0)
    packets: int = Field(ge=0)


class IPerf3Test(BaseModel):
    model_config = ConfigDict(strict=True, allow_inf_nan=False)

    cpu_util_total: float = Field(ge=0)
    cpu_util_user: float = Field(ge=0)
    cpu_util_system: float = Field(ge=0)
    sender_has_retransmits: int

    streams: list[IPerf3Stream] = Field(min_length=1, max_length=1)


def generate_cookie() -> bytes:
    cookie = "".join(secrets.choice(ascii_lowercase) for _ in range(36))
    return cookie.encode("ascii") + b"\x00"


def receive_state(sock: socket.socket, expected: int, msg_type: LogLevel) -> None:
    exp_fmt = format_state(expected)
    msg = sock.recv(1)

    if not msg:
        raise ConnectionError(f"Connection terminated unexpectedly: expected {exp_fmt}")

    actual = int.from_bytes(msg, signed=True)
    actual_fmt = format_state(actual)

    if actual != expected:
        raise ConnectionError(f"Received {actual_fmt}, expected {exp_fmt}")

    log_message(msg_type, f"Received {actual_fmt}")


def receive_bytes(sock: socket.socket, count: int) -> bytes:
    data = bytearray()

    while len(data) < count:
        chunk = sock.recv(count - len(data))

        if not chunk:
            raise ConnectionError(
                f"Connection closed unexpectedly: received {len(data)}/{count} bytes"
            )

        data.extend(chunk)

    return bytes(data)


def receive_json[T: BaseModel](sock: socket.socket, model: type[T], msg_type: LogLevel) -> T:
    length = int.from_bytes(receive_bytes(sock, 4))
    payload_bytes = receive_bytes(sock, length)
    log_json(msg_type, "Received", json.loads(payload_bytes))
    return model.model_validate_json(payload_bytes)


def send_state(sock: socket.socket, b: int, msg_type: LogLevel) -> None:
    sock.sendall(int.to_bytes(b))
    log_message(msg_type, f"Sent {format_state(b)}")


def send_json(sock: socket.socket, payload: dict[str, object], msg_type: LogLevel) -> None:
    payload_bytes = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
    len_bytes = len(payload_bytes).to_bytes(4)
    sock.sendall(len_bytes + payload_bytes)
    log_json(msg_type, "Sent", payload)


def format_state(value: int) -> str:
    try:
        name = State(value).name
    except ValueError:
        name = "UNKNOWN"

    return f"{name} ({value:#04x})"
