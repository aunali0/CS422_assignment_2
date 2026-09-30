import csv
import random
from dataclasses import dataclass
from pathlib import Path

from client import ClientConfig, try_run_test
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

    dest_servers = []
    server_idx = 0

    for i in range(1, count + 1):
        curr_attempt = 1

        while server_idx < len(shuffled_servers):
            server = shuffled_servers[server_idx]
            name = server.endpoint()

            if try_run_test(server.host, server.port, cfg, quiet=True):
                log_message("destinations", f"Server #{i}: successful test for {name}")
                dest_servers.append(server)

                break

            if curr_attempt == attempts:
                log_message(
                    "destinations",
                    f"Server #{i}: failed test for {name} on final attempt {attempts}/{attempts}",
                )
                break

            log_message(
                "destinations",
                f"Server #{i}: failed test for {name} on attempt {curr_attempt}/{attempts}",
            )

            curr_attempt += 1
            server_idx += 1

        if server_idx == len(shuffled_servers):
            break

        server_idx += 1

    if len(dest_servers) < count:
        log_message("destinations", f"Found {len(dest_servers)} out of {count} requested servers")
