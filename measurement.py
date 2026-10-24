# Per-sample records, run metadata, and CSV/JSON persistence (save and load).

import csv
import json
import math
import platform
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from log_utils import log_message
from tcp_info import TCP_INFO_FIELDS, TCP_INFO_UNITS, TcpInfo

# Loss proxy: TCP exposes no direct per-interval loss count, so we use the growth of
# tcpi_total_retrans (segments the sender retransmitted) over the sampling interval, and
# tcpi_bytes_retrans for the same signal in bytes. tcpi_lost is NOT cumulative -- it is
# the kernel's current estimate of segments considered lost in the in-progress recovery
# -- so it is logged as an instantaneous gauge (tcpi_lost) and never differenced.

SAMPLE_UNITS: dict[str, str] = {
    "run_id": "id",
    "destination": "host:port",
    "host": "hostname",
    "port": "port",
    "algorithm": "name",
    "time": "s",
    "interval": "s",
    "goodput": "Mbit/s",
    "bytes_acked_delta": "bytes",
    "retrans_delta": "segments",
    "bytes_retrans_delta": "bytes",
    "data_segs_out_delta": "segments",
    "delivered_delta": "segments",
    "retrans_rate": "fraction",
}

TCP_INFO_COLUMNS = tuple(f"tcpi_{name}" for name, _, _ in TCP_INFO_FIELDS)
CSV_COLUMNS = (*SAMPLE_UNITS, *TCP_INFO_COLUMNS)
CSV_UNITS = {**SAMPLE_UNITS, **{f"tcpi_{name}": unit for name, unit in TCP_INFO_UNITS.items()}}

CSV_NAME = "tcp-samples.csv"
METADATA_NAME = "test-metadata.json"

# Counter differences over one sampling interval; None when the kernel lacks the field.
DELTA_FIELDS = ("retrans_delta", "bytes_retrans_delta", "data_segs_out_delta", "delivered_delta")


@dataclass(frozen=True)
class Sample:
    time: float  # seconds since the first byte of the test
    interval: float  # seconds this sample covers
    goodput: float  # Mbit/s = (delta bytes acknowledged / delta t) * 8 / 1e6
    bytes_acked_delta: int
    retrans_delta: int | None
    bytes_retrans_delta: int | None
    data_segs_out_delta: int | None
    delivered_delta: int | None
    info: TcpInfo

    def retrans_rate(self) -> float | None:
        if self.retrans_delta is None or not self.data_segs_out_delta:
            return None
        return self.retrans_delta / self.data_segs_out_delta

    def ms(self, name: str) -> float | None:
        """A microsecond tcp_info field (rtt, rttvar, min_rtt) in milliseconds."""
        value = self.info[name]
        return None if value is None else value / 1000

    def rtt_ms(self) -> float | None:
        return self.ms("rtt")


@dataclass(frozen=True)
class RunMetadata:
    run_id: str
    host: str
    port: int
    algorithm: str
    duration: int
    goodput_interval: float
    started_at: str
    kernel: str
    tcp_info_bytes: int  # bytes the kernel actually wrote for struct tcp_info

    @classmethod
    def now(
        cls,
        run_id: str,
        host: str,
        port: int,
        algorithm: str,
        duration: int,
        interval: float,
        tcp_info_bytes: int,
    ) -> "RunMetadata":
        started = datetime.now(UTC).isoformat(timespec="seconds")
        return cls(
            run_id,
            host,
            port,
            algorithm,
            duration,
            interval,
            started,
            platform.release(),
            tcp_info_bytes,
        )

    def destination(self) -> str:
        return f"{self.host}:{self.port}"

    def slug(self) -> str:
        return re.sub(r"[^A-Za-z0-9._-]", "_", f"{self.run_id}_{self.host}_{self.port}")


type Run = tuple[RunMetadata, list[Sample]]


def percentile(data: list[float], fraction: float) -> float:
    """Linear interpolation at sorted index (n - 1) * fraction; works for n = 1."""
    ordered = sorted(data)
    position = (len(ordered) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def create_run_directory(out_dir: Path, run_id: str, category: str) -> Path:
    path = out_dir / category / run_id
    try:
        path.mkdir(parents=True)
    except FileExistsError:
        raise SystemExit(
            f"Output directory already exists: {path}. Choose a fresh --run-id."
        ) from None
    return path


def save_run(meta: RunMetadata, samples: list[Sample], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / CSV_NAME

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        for s in samples:
            writer.writerow(
                {
                    "run_id": meta.run_id,
                    "destination": meta.destination(),
                    "host": meta.host,
                    "port": meta.port,
                    "algorithm": meta.algorithm,
                    "time": round(s.time, 6),
                    "interval": round(s.interval, 6),
                    "goodput": round(s.goodput, 6),
                    "bytes_acked_delta": s.bytes_acked_delta,
                    **{name: getattr(s, name) for name in DELTA_FIELDS},
                    "retrans_rate": s.retrans_rate(),
                    **{f"tcpi_{name}": value for name, value in s.info.items()},
                }
            )

    metadata = {
        "run_id": meta.run_id,
        "destination": meta.destination(),
        "host": meta.host,
        "port": meta.port,
        "algorithm": meta.algorithm,
        "duration_s": meta.duration,
        "goodput_interval_s": meta.goodput_interval,
        "started_at": meta.started_at,
        "host_kernel": meta.kernel,
        "tcp_info_bytes": meta.tcp_info_bytes,
        "samples": len(samples),
        "units": CSV_UNITS,
    }
    (out_dir / METADATA_NAME).write_text(json.dumps(metadata, indent=2))

    log_message("test", f"Measurements saved to {csv_path}")
    return csv_path


def load_run(csv_path: Path) -> Run:
    """Inverse of save_run: rebuild metadata and samples from a saved trace directory."""
    data = json.loads((csv_path.parent / METADATA_NAME).read_text())
    meta = RunMetadata(
        run_id=data["run_id"],
        host=data["host"],
        port=data["port"],
        algorithm=data["algorithm"],
        duration=data["duration_s"],
        goodput_interval=data["goodput_interval_s"],
        started_at=data["started_at"],
        kernel=data["host_kernel"],
        tcp_info_bytes=data["tcp_info_bytes"],
    )

    def integer(value: str) -> int | None:
        return int(value) if value else None

    with csv_path.open(newline="") as f:
        samples = [
            Sample(
                time=float(row["time"]),
                interval=float(row["interval"]),
                goodput=float(row["goodput"]),
                bytes_acked_delta=int(row["bytes_acked_delta"]),
                **{name: integer(row[name]) for name in DELTA_FIELDS},
                info={name: integer(row[f"tcpi_{name}"]) for name, _, _ in TCP_INFO_FIELDS},
            )
            for row in csv.DictReader(f)
        ]

    return meta, samples


def load_runs(run_dir: Path) -> list[Run]:
    """Every saved trace under <run_dir>/tcp-traces, in name order."""
    return [load_run(path) for path in sorted(run_dir.glob(f"tcp-traces/*/{CSV_NAME}"))]
