import csv
import random
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from client import ClientConfig, TestResult, try_run_test
from log_utils import log_message
from measurement import create_run_directory, save_run
from plots import (
    GOODPUT_GRAPHS_NAME,
    SUMMARY_TABLE_NAME,
    Run,
    plot_destinations,
    save_run_plots,
    save_summary_table,
)


@dataclass
class Server:
    host: str
    port: int

    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"


def load_servers(filepath: Path) -> list[Server]:
    servers: list[Server] = []

    with open(filepath) as f:
        reader = csv.DictReader(f)

        for row in reader:
            port = int(row["PORT"].split("-")[0])
            servers.append(Server(row["IP/HOST"], port))

    return servers


def representative(runs: list[Run]) -> Run:
    # Q2(b) asks for one representative destination. The highest median goodput is the
    # destination least likely to have been limited by a rate-limited or overloaded
    # server, so it shows congestion-control behaviour most clearly.
    return max(runs, key=lambda run: median([sample.goodput for sample in run[1]]))


def run_destinations(
    servers: list[Server], count: int, attempts: int, cfg: ClientConfig, run_id: str, out_dir: Path
) -> None:
    out = create_run_directory(out_dir, run_id, "destination-tests")
    plots_dir = out / "plots"
    reports_dir = out / "reports"
    plots_dir.mkdir()
    reports_dir.mkdir()

    shuffled_servers = servers.copy()
    random.shuffle(shuffled_servers)
    server_idx = 0

    tested_servers: list[tuple[Server, TestResult]] = []

    for i in range(count):
        curr_attempt = 1

        while server_idx < len(shuffled_servers):
            server = shuffled_servers[server_idx]
            attempt_label = f"Server {i + 1}/{count} | attempt {curr_attempt}/{attempts}"
            dest_run_id = f"{run_id}-d{i + 1}"
            test_result = try_run_test(server.host, server.port, cfg, dest_run_id, quiet=True)

            if test_result is not None:
                log_message("destinations", f"{attempt_label} | passed: {server.endpoint()}")
                save_run(
                    test_result.metadata,
                    test_result.samples,
                    out / "tcp-traces" / test_result.metadata.slug(),
                )
                tested_servers.append((server, test_result))

                break

            if curr_attempt == attempts:
                log_message("destinations", f"{attempt_label} | failed; limit reached")
                break

            log_message("destinations", f"{attempt_label} | failed; trying next server")

            curr_attempt += 1
            server_idx += 1

        if server_idx == len(shuffled_servers):
            break

        server_idx += 1

    log_message("destinations", f"Selected {len(tested_servers)}/{count} servers")

    runs: list[Run] = [(result.metadata, result.samples) for _, result in tested_servers]

    save_summary_table(runs, reports_dir / SUMMARY_TABLE_NAME)
    plot_destinations(runs, plots_dir / GOODPUT_GRAPHS_NAME)

    if runs:
        meta, samples = representative(runs)
        log_message("destinations", f"Representative destination: {meta.destination()}")
        save_run_plots(meta, samples, out / "tcp-traces" / meta.slug())
