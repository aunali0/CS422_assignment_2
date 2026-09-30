import csv
import random
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path

from pydantic import ValidationError

from client import run_test, ClientConfig
from reporting import log_message


@dataclass
class Server:
    host: str
    port: int


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

    success_count = 0
    attempts_pending = 0

    for server in shuffled_servers:
        try:
            run_test(server.host, server.port, cfg)
        except (OSError, JSONDecodeError, UnicodeDecodeError, ValidationError) as err:
            log_message("error", f"{server.host}:{server.port} | {type(err).__name__}: {err}")

            if attempts_pending == attempts:
                return

            attempts_pending += 1
            continue

        dest_servers.append(server)
        print(server)

        attempts_pending = 0
        success_count += 1

        if success_count == count:
            break
