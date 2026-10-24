import csv
import random
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from client import ClientConfig, try_run_test
from log_utils import log_message
from measurement import Run, create_run_directory, save_run
from plots import save_destination_outputs


@dataclass
class Server:
    host: str
    port: int

    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"


def load_servers(filepath: Path) -> list[Server]:
    with open(filepath) as f:
        # For a port range such as "5201-5209", use the first port.
        return [Server(row["IP/HOST"], int(row["PORT"].split("-")[0])) for row in csv.DictReader(f)]


def representative(runs: list[Run]) -> Run:
    # Q2(b) asks for one representative destination. The highest median goodput is the
    # destination least likely to have been limited by a rate-limited or overloaded
    # server, so it shows congestion-control behaviour most clearly.
    return max(runs, key=lambda run: median(sample.goodput for sample in run[1]))


def run_destinations(
    servers: list[Server], count: int, attempts: int, cfg: ClientConfig, run_id: str, out_dir: Path
) -> None:
    out = create_run_directory(out_dir, run_id, "destination-tests")

    # Each attempt consumes the next untried server, so no server is tested twice.
    candidates = iter(random.sample(servers, len(servers)))
    runs: list[Run] = []

    for slot in range(1, count + 1):
        for attempt in range(1, attempts + 1):
            server = next(candidates, None)
            if server is None:
                break

            label = f"Server {slot}/{count} | attempt {attempt}/{attempts} | {server.endpoint()}"
            result = try_run_test(server.host, server.port, cfg, f"{run_id}-d{slot}", quiet=True)
            log_message("destinations", f"{label} | {'passed' if result else 'failed'}")

            if result is not None:
                save_run(
                    result.metadata, result.samples, out / "tcp-traces" / result.metadata.slug()
                )
                runs.append((result.metadata, result.samples))
                break

        if server is None:
            log_message("destinations", "Server list exhausted")
            break

    shortfall = f" (shortfall: {count - len(runs)})" if len(runs) < count else ""
    log_message("destinations", f"Selected {len(runs)}/{count} servers{shortfall}")

    save_destination_outputs(runs, out)
    if runs:
        meta, _ = representative(runs)
        log_message("destinations", f"Representative destination: {meta.destination()}")
