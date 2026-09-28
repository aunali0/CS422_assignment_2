import argparse
import json
import secrets
import socket
import time
from enum import IntEnum
from string import ascii_lowercase
from typing import Literal

Stage = Literal["connect", "control", "data", "test"]

BUF_SIZE: int = 131072
NOTIF_INTERVAL_SEC: float = 0.5

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


def to_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be an integer")


def port_type(value: str) -> int:
    port = to_int(value)

    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535 (inclusive)")

    return port


def positive_int_type(value: str) -> int:
    num = to_int(value)

    if num <= 0:
        raise argparse.ArgumentTypeError("must be positive")

    return num


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CLI for CS422 Assignment 2")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser(
        "run",
        help="Run a TCP client that connects to an iPERF3 server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    dest = run.add_argument_group("destination")
    dest.add_argument("--host", required=True, help="Server hostname or IP address")
    dest.add_argument("--port", type=port_type, default=5201, help="Server TCP port")

    experiment = run.add_argument_group("experiment")
    experiment.add_argument(
        "--duration",
        type=positive_int_type,
        default=5,
        metavar="SECONDS",
        help="Experiment duration in seconds",
    )

    timeouts = run.add_argument_group("timeouts")
    timeouts.add_argument(
        "--connect-timeout",
        type=positive_int_type,
        default=5,
        metavar="SECONDS",
        help="Timeout in seconds for establishing connection with server",
    )
    timeouts.add_argument(
        "--control-timeout",
        type=positive_int_type,
        default=5,
        metavar="SECONDS",
        help="Timeout in seconds for exchanging control packets with server",
    )
    timeouts.add_argument(
        "--data-timeout",
        type=positive_int_type,
        default=5,
        metavar="SECONDS",
        help="Timeout in seconds for uploading data packets to server",
    )

    return parser


def notify(stage: Stage, msg: str) -> None:
    print(f"{f'[{stage}]':<9} {msg}", flush=True)


def format_state(value: int) -> str:
    try:
        name = State(value).name
    except ValueError:
        name = "UNKNOWN"

    return f"{name} ({value:#04x})"


def generate_cookie() -> bytes:
    cookie = "".join(secrets.choice(ascii_lowercase) for _ in range(36))
    return cookie.encode("ascii") + b"\x00"


def get_servername(sock: socket.socket) -> str:
    host, port, *_ = sock.getpeername()
    return f"{host}:{port}"


def receive_state(sock: socket.socket, expected: int, stage: Stage) -> None:
    msg = sock.recv(1)

    if not msg:
        raise ConnectionError("Connection terminated unexpectedly")

    actual = int.from_bytes(msg)

    if actual != expected:
        raise ConnectionError(f"Received {format_state(actual)}, expected {format_state(expected)}")

    notify(stage, f"Received {format_state(actual)}")


def send_byte(sock: socket.socket, b: int, stage: Stage) -> None:
    sock.sendall(int.to_bytes(b))
    notify(stage, f"Sent {format_state(b)}")


def send_json(sock: socket.socket, payload: dict[str, object], stage: Stage) -> None:
    payload_bytes = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
    payload_len = len(payload_bytes)
    sock.sendall(payload_len.to_bytes(4) + payload_bytes)
    notify(stage, f"Sent JSON ({payload_len} bytes)")


def notify_data_interval(bytes_sent: int, time_passed: float, duration: int) -> None:
    notify("data", f"{time_passed:.1f}s / {duration}s | {bytes_sent / (1024 * 1024):.2f} MiB sent")


def run_client(
    host: str,
    port: int,
    duration: int,
    connect_timeout: int,
    control_timeout: int,
    data_timeout: int,
):
    cookie = generate_cookie()

    with socket.create_connection((host, port), timeout=connect_timeout) as control_sock:
        notify("connect", f"Established control connection to {host}:{port}")
        control_sock.settimeout(control_timeout)

        control_sock.sendall(cookie)
        notify("control", "Sent cookie")

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

        bytes_sent = 0

        with socket.create_connection((host, port), timeout=connect_timeout) as data_sock:
            notify("data", f"Established data connection with {host}:{port}")
            data_sock.settimeout(data_timeout)

            data_sock.sendall(cookie)
            notify("data", "Sent cookie")

            receive_state(control_sock, State.TEST_START, "control")
            receive_state(control_sock, State.TEST_RUNNING, "control")

            notify("data", f"Sending data for {duration}s...")

            data_payload = secrets.token_bytes(BUF_SIZE)

            start_time = time.monotonic()
            next_notif_time = start_time + NOTIF_INTERVAL_SEC

            while True:
                curr_time = time.monotonic()
                time_passed = curr_time - start_time
                time_rem = duration - time_passed

                if time_rem <= 0:
                    break

                if curr_time >= next_notif_time:
                    notify_data_interval(bytes_sent, time_passed, duration)
                    next_notif_time += NOTIF_INTERVAL_SEC

                data_sock.settimeout(time_rem)

                try:
                    bytes_sent += data_sock.send(data_payload)
                except TimeoutError:
                    break

        notify_data_interval(bytes_sent, duration, duration)

        send_byte(control_sock, State.TEST_END, "control")
        receive_state(control_sock, State.EXCHANGE_RESULTS, "control")

        # TODO: Implement final sequence where client and server exchange statistics

        tcp_upload_payload: dict[str, object] = {"bytes": bytes_sent}
        send_json(control_sock, tcp_upload_payload, "control")


def main() -> None:
    args = create_parser().parse_args()

    if args.command == "run":
        run_client(
            args.host,
            args.port,
            args.duration,
            args.connect_timeout,
            args.control_timeout,
            args.data_timeout,
        )


if __name__ == "__main__":
    main()
