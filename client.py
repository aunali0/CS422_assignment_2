import resource
import secrets
import socket
import time
from contextlib import nullcontext
from dataclasses import dataclass
from json import JSONDecodeError


from protocol import (
    IPerf3Test,
    State,
    generate_cookie,
    receive_json,
    receive_state,
    send_json,
    send_state,
)
from log_utils import log_message, log_test_progress, suppress_logging
from pydantic import ValidationError

BUF_SIZE = 131072


@dataclass
class ClientConfig:
    duration: int
    print_interval: float
    connect_timeout: float
    control_timeout: float
    data_timeout: float


def run_test(host: str, port: int, cfg: ClientConfig) -> None:
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

            data_payload = secrets.token_bytes(BUF_SIZE)

            start_time = time.monotonic()
            end_time = start_time + cfg.duration

            usage_start = resource.getrusage(resource.RUSAGE_SELF)
            bytes_sent = 0

            next_notif_time = start_time + cfg.print_interval

            while True:
                curr_time = time.monotonic()
                time_rem = end_time - curr_time

                if time_rem <= 0:
                    break

                if curr_time >= next_notif_time:
                    log_test_progress(bytes_sent, curr_time - start_time, cfg.duration)
                    next_notif_time += cfg.print_interval

                data_sock.settimeout(min(cfg.data_timeout, time_rem))

                try:
                    bytes_sent += data_sock.send(data_payload)
                except TimeoutError:
                    if time.monotonic() < end_time:
                        raise
                    break

            time_elapsed = time.monotonic() - start_time
            usage_end = resource.getrusage(resource.RUSAGE_SELF)

            log_test_progress(bytes_sent, time_elapsed, cfg.duration)

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
        send_json(control_sock, test_payload, "control")
        receive_json(control_sock, IPerf3Test, "control")

        receive_state(control_sock, State.DISPLAY_RESULTS, "control")
        send_state(control_sock, State.IPERF_DONE, "control")


def try_run_test(host: str, port: int, cfg: ClientConfig, quiet: bool = False) -> bool:
    try:
        with suppress_logging() if quiet else nullcontext():
            run_test(host, port, cfg)

    except (OSError, JSONDecodeError, UnicodeDecodeError, ValidationError) as err:
        log_message("error", f"{host}:{port} | {type(err).__name__}: {err}")
        return False

    return True
