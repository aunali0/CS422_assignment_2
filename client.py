import resource
import secrets
import socket
import struct
import time
from contextlib import nullcontext
from dataclasses import dataclass, field
from json import JSONDecodeError
from typing import NamedTuple

from pydantic import ValidationError

from log_utils import log_message, suppress_logging
from protocol import (
    IPerf3Test,
    State,
    generate_cookie,
    receive_json,
    receive_state,
    send_json,
    send_state,
)

BUF_SIZE = 131072

BYTES_ACK_OFFSET = 120
TCP_INFO_SIZE = BYTES_ACK_OFFSET + 8


@dataclass(frozen=True)
class ClientConfig:
    duration: int
    print_interval: float
    goodput_interval: float
    connect_timeout: float
    control_timeout: float
    data_timeout: float


class GoodputSample(NamedTuple):
    time: float
    value: float


@dataclass
class TestResult:
    goodput: list[GoodputSample] = field(default_factory=list)
    algorithm: str = "unknown"


def get_bytes_ack(sock: socket.socket) -> int:
    tcp_info_bytes = sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO, TCP_INFO_SIZE)
    return struct.unpack_from("=Q", tcp_info_bytes, BYTES_ACK_OFFSET)[0]


def get_tcp_algorithm(sock: socket.socket) -> str:
    tcp_alg_bytes = sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_CONGESTION, 16)
    return tcp_alg_bytes.split(b"\x00", 1)[0].decode("ascii")


def run_test(host: str, port: int, cfg: ClientConfig) -> TestResult:
    cookie = generate_cookie()

    with socket.create_connection((host, port), timeout=cfg.connect_timeout) as control_sock:
        log_message("control", f"Connected to {host}:{port}")
        control_sock.settimeout(cfg.control_timeout)

        control_sock.sendall(cookie)
        log_message("control", "Sent cookie")

        receive_state(control_sock, State.PARAM_EXCHANGE, "control")

        control_payload: dict[str, object] = {
            "tcp": True,
            "omit": 0,
            "time": cfg.duration,
            "num": 0,
            "blockcount": 0,
            "parallel": 1,
            "len": BUF_SIZE,
        }
        send_json(control_sock, control_payload, "control")

        receive_state(control_sock, State.CREATE_STREAMS, "control")

        with socket.create_connection((host, port), timeout=cfg.connect_timeout) as data_sock:
            log_message("data", "Connected")
            data_sock.settimeout(cfg.data_timeout)

            data_sock.sendall(cookie)
            log_message("data", "Sent cookie")

            receive_state(control_sock, State.TEST_START, "control")
            receive_state(control_sock, State.TEST_RUNNING, "control")

            log_message("test", f"Uploading for {cfg.duration}s")

            test_payload = secrets.token_bytes(BUF_SIZE)
            algorithm = get_tcp_algorithm(data_sock)

            start_time = time.monotonic()
            end_time = start_time + cfg.duration

            usage_start = resource.getrusage(resource.RUSAGE_SELF)
            total_bytes_sent = 0

            next_print_time = start_time + cfg.print_interval
            next_goodput_time = start_time + cfg.goodput_interval
            data_deadline = start_time + cfg.data_timeout

            prev_bytes_ack = get_bytes_ack(data_sock)
            prev_goodput_time = start_time
            goodputs: list[GoodputSample] = []

            def sample_goodput(sample_time: float) -> None:
                nonlocal prev_bytes_ack, prev_goodput_time

                bytes_ack = get_bytes_ack(data_sock)
                bytes_ack_delta = bytes_ack - prev_bytes_ack
                time_delta = sample_time - prev_goodput_time
                goodput = bytes_ack_delta / time_delta * 8 / 1_000_000
                goodputs.append(GoodputSample(sample_time - start_time, goodput))

                prev_bytes_ack = bytes_ack
                prev_goodput_time = sample_time

            def log_test_progress(time_passed: float) -> None:
                sent = total_bytes_sent / (1024 * 1024)
                log_message("test", f"{time_passed:.1f}s / {cfg.duration}s | {sent:.1f} MiB sent")

            while True:
                curr_time = time.monotonic()
                time_rem = end_time - curr_time
                time_elapsed = curr_time - start_time

                if time_rem <= 0:
                    break

                if curr_time >= data_deadline:
                    raise TimeoutError("Data socket timed out")

                if curr_time >= next_goodput_time:
                    sample_goodput(curr_time)
                    next_goodput_time = curr_time + cfg.goodput_interval

                if curr_time >= next_print_time:
                    log_test_progress(time_elapsed)
                    next_print_time = curr_time + cfg.print_interval

                deadline = min(next_goodput_time, next_print_time, end_time, data_deadline)
                data_timeout = deadline - time.monotonic()

                if data_timeout <= 0:
                    continue

                data_sock.settimeout(data_timeout)

                try:
                    bytes_sent = data_sock.send(test_payload)
                except TimeoutError:
                    continue

                if bytes_sent == 0:
                    raise ConnectionError("Data connection closed during test")

                total_bytes_sent += bytes_sent
                data_deadline = time.monotonic() + cfg.data_timeout

            curr_time = time.monotonic()
            time_elapsed = curr_time - start_time

            sample_goodput(curr_time)
            log_test_progress(time_elapsed)

            usage_end = resource.getrusage(resource.RUSAGE_SELF)

            send_state(control_sock, State.TEST_END, "control")
            receive_state(control_sock, State.EXCHANGE_RESULTS, "control")

        user_time = usage_end.ru_utime - usage_start.ru_utime
        sys_time = usage_end.ru_stime - usage_start.ru_stime

        cpu_util_user = user_time / time_elapsed * 100
        cpu_util_sys = sys_time / time_elapsed * 100
        cpu_util_total = cpu_util_user + cpu_util_sys

        test_payload: dict[str, object] = {
            "cpu_util_total": cpu_util_total,
            "cpu_util_user": cpu_util_user,
            "cpu_util_system": cpu_util_sys,
            "sender_has_retransmits": 0,
            "streams": [
                {
                    "id": 1,
                    "bytes": total_bytes_sent,
                    "retransmits": -1,
                    "jitter": 0,
                    "errors": 0,
                    "packets": 0,
                    "start_time": 0,
                    "end_time": time_elapsed,
                }
            ],
        }
        send_json(control_sock, test_payload, "control")
        receive_json(control_sock, IPerf3Test, "control")

        receive_state(control_sock, State.DISPLAY_RESULTS, "control")
        send_state(control_sock, State.IPERF_DONE, "control")

        return TestResult(goodputs, algorithm)


def try_run_test(host: str, port: int, cfg: ClientConfig, quiet: bool = False) -> TestResult | None:
    try:
        with suppress_logging() if quiet else nullcontext():
            return run_test(host, port, cfg)

    except (OSError, JSONDecodeError, UnicodeDecodeError, ValidationError) as err:
        log_message("error", f"{host}:{port} | {type(err).__name__}: {err}")
