import argparse
import json
import resource
import secrets
import socket
import time
from enum import IntEnum
from string import ascii_lowercase
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BUF_SIZE = 131072
LOG_PREFIX_WIDTH = 9

LogMsgType = Literal["control", "data"]


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


class StreamResult(BaseModel):
    model_config = ConfigDict(strict=True, allow_inf_nan=False)

    id: Literal[1]
    bytes: int = Field(ge=0)
    retransmits: int
    jitter: float = Field(ge=0)
    errors: int = Field(ge=0)
    packets: int = Field(ge=0)


class TestResult(BaseModel):
    model_config = ConfigDict(strict=True, allow_inf_nan=False)

    cpu_util_total: float = Field(ge=0)
    cpu_util_user: float = Field(ge=0)
    cpu_util_system: float = Field(ge=0)
    sender_has_retransmits: int

    streams: list[StreamResult] = Field(min_length=1, max_length=1)


def to_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be an integer") from None


def to_float(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a float") from None


def port_type(value: str) -> int:
    port = to_int(value)

    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535 (inclusive)")

    return port


def check_positive[T: (int, float)](num: T) -> T:
    if num <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return num


def positive_int_type(value: str) -> int:
    return check_positive(to_int(value))


def positive_float_type(value: str) -> float:
    return check_positive(to_float(value))


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CLI for CS422 Assignment 2")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser(
        "run",
        help="Run a TCP client that communicates with an iPERF3 server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    server = run.add_argument_group("server")
    server.add_argument("--host", required=True, help="Server hostname or IP address")
    server.add_argument("--port", type=port_type, default=5201, help="Server TCP port")

    experiment = run.add_argument_group("experiment")
    experiment.add_argument(
        "--duration",
        type=positive_int_type,
        default=10,
        metavar="SECONDS",
        help="Experiment duration in seconds",
    )
    experiment.add_argument(
        "--print-interval",
        type=positive_float_type,
        default=1.0,
        metavar="SECONDS",
        help="How often experiment progress is printed",
    )

    timeouts = run.add_argument_group("timeouts")
    timeouts.add_argument(
        "--connect-timeout",
        type=positive_int_type,
        default=5,
        metavar="SECONDS",
        help="Timeout for establishing connection with server",
    )
    timeouts.add_argument(
        "--control-timeout",
        type=positive_int_type,
        default=5,
        metavar="SECONDS",
        help="Timeout for sending control packets to server",
    )
    timeouts.add_argument(
        "--data-timeout",
        type=positive_int_type,
        default=5,
        metavar="SECONDS",
        help="Timeout for sending data packets to server",
    )

    return parser


def generate_cookie() -> bytes:
    cookie = "".join(secrets.choice(ascii_lowercase) for _ in range(36))
    return cookie.encode("ascii") + b"\x00"


def log_message(msg_type: LogMsgType, msg: str) -> None:
    print(f"{f'[{msg_type}]':<{LOG_PREFIX_WIDTH}} {msg}")


def log_json(msg_type: LogMsgType, action: str, payload: object) -> None:
    log_message(msg_type, f"{action} JSON:")
    json_fmt = json.dumps(payload, indent=2, ensure_ascii=False)

    for line in json_fmt.splitlines():
        print(f"{'':{LOG_PREFIX_WIDTH}} {line}")


def log_data_progress(bytes_sent: int, time_passed: float, duration: int) -> None:
    log_message("data", f"{time_passed:.1f}s / {duration}s | {bytes_sent / (1024 * 1024):.2f} MiB sent")


def format_state(value: int) -> str:
    try:
        name = State(value).name
    except ValueError:
        name = "UNKNOWN"

    return f"{name} ({value:#04x})"


def receive_state(sock: socket.socket, expected: int, msg_type: LogMsgType) -> None:
    exp_fmt = format_state(expected)
    msg = sock.recv(1)

    if not msg:
        raise ConnectionError(f"Connection terminated unexpectedly: expected {exp_fmt}")

    actual = int.from_bytes(msg)
    actual_fmt = format_state(actual)

    if actual != expected:
        raise ConnectionError(f"Received {actual_fmt}: expected {exp_fmt}")

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


def receive_json[T: BaseModel](sock: socket.socket, model: type[T], msg_type: LogMsgType) -> T:
    length = int.from_bytes(receive_bytes(sock, 4))
    payload_bytes = receive_bytes(sock, length)
    log_json(msg_type, "Received", json.loads(payload_bytes))
    return model.model_validate_json(payload_bytes)


def send_state(sock: socket.socket, b: int, msg_type: LogMsgType) -> None:
    sock.sendall(int.to_bytes(b))
    log_message(msg_type, f"Sent {format_state(b)}")


def send_json(sock: socket.socket, payload: dict[str, object], msg_type: LogMsgType) -> None:
    payload_bytes = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
    len_bytes = len(payload_bytes).to_bytes(4)
    sock.sendall(len_bytes + payload_bytes)
    log_json(msg_type, "Sent", payload)


def run_client(
    host: str,
    port: int,
    duration: int,
    print_interval: float,
    connect_timeout: int,
    control_timeout: int,
    data_timeout: int,
):
    cookie = generate_cookie()

    with socket.create_connection((host, port), timeout=connect_timeout) as control_sock:
        log_message("control", f"Established control connection to {host}:{port}")
        control_sock.settimeout(control_timeout)

        control_sock.sendall(cookie)
        log_message("control", "Sent cookie")

        receive_state(control_sock, State.PARAM_EXCHANGE, "control")

        control_payload: dict[str, object] = {
            "tcp": True,
            "omit": 0,
            "time": duration,
            "num": 0,
            "blockcount": 0,
            "parallel": 1,
            "len": BUF_SIZE,
        }
        send_json(control_sock, control_payload, "control")

        receive_state(control_sock, State.CREATE_STREAMS, "control")

        with socket.create_connection((host, port), timeout=connect_timeout) as data_sock:
            log_message("data", f"Established data connection with {host}:{port}")
            data_sock.settimeout(data_timeout)

            data_sock.sendall(cookie)
            log_message("data", "Sent cookie")

            receive_state(control_sock, State.TEST_START, "control")
            receive_state(control_sock, State.TEST_RUNNING, "control")

            log_message("data", f"Sending data for {duration}s...")

            data_payload = secrets.token_bytes(BUF_SIZE)

            start_time = time.monotonic()
            usage_start = resource.getrusage(resource.RUSAGE_SELF)
            bytes_sent = 0

            next_notif_time = start_time + print_interval

            while True:
                curr_time = time.monotonic()
                time_passed = curr_time - start_time
                time_rem = duration - time_passed

                if time_rem <= 0:
                    break

                if curr_time >= next_notif_time:
                    log_data_progress(bytes_sent, time_passed, duration)
                    next_notif_time += print_interval

                data_sock.settimeout(time_rem)

                try:
                    bytes_sent += data_sock.send(data_payload)
                except TimeoutError:
                    break

            time_elapsed = time.monotonic() - start_time
            usage_end = resource.getrusage(resource.RUSAGE_SELF)

            log_data_progress(bytes_sent, time_passed, duration)

            send_state(control_sock, State.TEST_END, "control")
            receive_state(control_sock, State.EXCHANGE_RESULTS, "control")

        user_time = usage_end.ru_utime - usage_start.ru_utime
        sys_time = usage_end.ru_stime - usage_start.ru_stime

        cpu_util_user = user_time / time_elapsed * 100
        cpu_util_sys = sys_time / time_elapsed * 100
        cpu_util_total = cpu_util_user + cpu_util_sys

        client_results: dict[str, object] = {
            "cpu_util_total": cpu_util_total,
            "cpu_util_user": cpu_util_user,
            "cpu_util_system": cpu_util_sys,
            "sender_has_retransmits": 0,
            "streams": [
                {
                    "id": 1,
                    "bytes": bytes_sent,
                    "retransmits": -1,
                    "jitter": 0,
                    "errors": 0,
                    "packets": 0,
                    "start_time": 0,
                    "end_time": time_elapsed,
                }
            ],
        }
        send_json(control_sock, client_results, "control")
        receive_json(control_sock, TestResult, "control")

        receive_state(control_sock, State.DISPLAY_RESULTS, "control")
        send_state(control_sock, State.IPERF_DONE, "control")


def main() -> None:
    args = create_parser().parse_args()

    if args.command == "run":
        run_client(
            args.host,
            args.port,
            args.duration,
            args.print_interval,
            args.connect_timeout,
            args.control_timeout,
            args.data_timeout,
        )


if __name__ == "__main__":
    main()
