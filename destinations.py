import csv
import random
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from client import ClientConfig, TestResult, try_run_test
from log_utils import log_message


@dataclass
class Server:
    host: str
    port: int

    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"


def load_servers(filepath: Path) -> list[Server]:
    servers = []

    with open(filepath) as f:
        reader = csv.DictReader(f)

        for row in reader:
            port = int(row["PORT"].split("-")[0])
            servers.append(Server(row["IP/HOST"], port))

    return servers


def run_destinations(servers: list[Server], count: int, attempts: int, cfg: ClientConfig) -> None:
    shuffled_servers = servers.copy()
    random.shuffle(shuffled_servers)
    server_idx = 0

    tested_servers: list[tuple[Server, TestResult]] = []

    for i in range(count):
        curr_attempt = 1

        while server_idx < len(shuffled_servers):
            server = shuffled_servers[server_idx]
            attempt_label = f"Server {i + 1}/{count} | attempt {curr_attempt}/{attempts}"
            test_result = try_run_test(server.host, server.port, cfg, quiet=True)

            if test_result is not None:
                log_message("destinations", f"{attempt_label} | passed: {server.endpoint()}")
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

    num_dest = len(tested_servers)
    log_message("destinations", f"Selected {num_dest}/{count} servers")

    fig, ax = plt.subplots(1, 1, figsize=(11, 6), layout="constrained")

    for server, test_result in tested_servers:
        x, y = zip(*test_result.goodput, strict=True)
        label = f"{server.endpoint()} ({test_result.algorithm})"
        ax.plot(x, y, label=label, linewidth=1.5)

    ax.set_title("Throughput Per Destination", fontsize=14)
    ax.set_xlabel("Time (s)", fontsize=12)
    ax.set_ylabel("Throughput (Mbit/s)", fontsize=12)

    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.tick_params(axis="both", labelsize=10)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.grid(axis="y", linestyle="--", alpha=0.25, linewidth=0.7)
    ax.set_axisbelow(True)

    fig.legend(loc="outside lower center", ncols=2, fontsize=10)

    fig.savefig("destinations.pdf", format="pdf", bbox_inches="tight")
    log_message("destinations", "Plot saved to destinations.pdf")
