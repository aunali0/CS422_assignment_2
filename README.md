# CS 422 Assignment 2 — iPerf3 Client, TCP Statistics, and Congestion Control

A from-scratch Python implementation of the iperf3 client protocol. It opens the control
connection, performs the JSON parameter exchange, opens a separate data connection,
uploads for a configurable duration, and terminates the test following iperf3 semantics.
While the transfer runs it samples `TCP_INFO` from the **data** socket to record goodput,
congestion window, RTT, and a loss proxy, then writes raw measurements and PDF plots.

The iperf3 binary is never invoked; the client talks to standard public iperf3 servers.

## Assignment 2 Q3

**Open [Q3_REPORT.pdf](Q3_REPORT.pdf) for the five-page Q3 report.**

See [Q3_RUN.md](Q3_RUN.md) for the CUBIC/Reno/BBR experiment and Docker commands,
outputs, and submission steps. [Q3_DESIGN.md](Q3_DESIGN.md) contains the proposed
algorithm and Assignment 3 handoff. The completed comparison, checked measurements, and
reviewed report are linked from [Q3_RESULTS.md](Q3_RESULTS.md).

```sh
python main.py compare -s iperf3-servers.csv -c 10 -t 60 -g 1 -r 3 --run-id q3-final
python main.py analyze --manifest results/q3-final/manifest.json
```

## Requirements

**This must run on Linux** — either a Linux machine or Windows with WSL2. It reads
`getsockopt(TCP_INFO)` and imports the Unix-only `resource` module, so it cannot run on
Windows directly (it fails at import, even for `--help`).

Use Python 3.12 or newer. Install the dependencies in a virtual environment:

```sh
cd /path/to/CS422_assignment_2
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

With the environment activated, use `python` for the commands below. Alternatively,
install uv and use `uv run`; it resolves dependencies from pyproject.toml.

> On Windows, open your WSL shell first and work from the mounted path, e.g.
> `cd /mnt/c/Users/<you>/Documents/CS422/CS422_assignment_2`.

## Running

### One server

```bash
python main.py test -s 185.180.12.40 -p 5201 -t 15 -g 0.5
```

Uploads to one iperf3 server for 15 seconds, sampling every 0.5 s. Good for a quick check
that everything works before committing to longer runs.

### Many servers (the main experiment)

```bash
python main.py destinations -s iperf3-servers.csv -c 10 -a 3 -t 60 -g 1
```

Picks 10 random servers from `iperf3-servers.csv`, runs a 60 s test against each, and
retries up to 3 servers per destination if one refuses, rate-limits, or times out. Any
shortfall against the requested count is reported at the end.

Public iperf3 servers are frequently busy or offline. Failures are expected and handled;
the run continues with a replacement server.

## Options

The test, destinations, and compare subcommands share these:

| Option | Default | Meaning |
| --- | --- | --- |
| `--algorithm NAME` | OS default | Select the data socket algorithm before connecting (test/destinations) |
| `-t, --time SECONDS` | 60 | Transfer duration per destination |
| `-g, --goodput-interval SECONDS` | 1 | Sampling interval for goodput and TCP stats |
| `-i, --print-interval SECONDS` | 5 | How often progress is printed |
| `-o, --out-dir DIR` | `results` | Where measurements and plots are written |
| `--run-id ID` | UTC timestamp | Run identifier recorded in every output file |
| `--connect-timeout SECONDS` | 5 | Connection establishment timeout |
| `--control-timeout SECONDS` | 3 | Control socket timeout |
| `--data-timeout SECONDS` | 3 | Data socket idle timeout |

`test` additionally takes `-s, --host` (required) and `-p, --port` (default 5201).
`destinations` takes `-s, --servers` (CSV path, required), `-c, --count` (default 10),
and `-a, --attempts` (default 3).

Run `python main.py test --help` for the full list.

## Output

Everything lands in `results/` (or `--out-dir`), named
`<run-id>_<host>_<port>`:

| File | Contents |
| --- | --- |
| `*.csv` | One row per sample, 73 columns: goodput, interval deltas, and every decoded `tcp_info` field (`tcpi_*`) |
| `*.json` | Run metadata — destination, algorithm, kernel, sampling interval, and the **unit of every CSV column** |
| `*-timeseries.pdf` | Q2(b)(i): `snd_cwnd`, RTT, loss proxy, and goodput against time |
| `*-scatter.pdf` | Q2(b)(ii): `snd_cwnd`, RTT, and loss signal each against goodput |
| `goodput-graphs.pdf` | Q1: goodput over time, one panel per destination |
| `goodput-summary.pdf` | Q1: min / median / mean / 95th-percentile goodput per destination |

The `destinations` run also picks a **representative destination** — the one with the
highest median goodput, least likely to have been throttled — and emits the two Q2 plots
for it.

## How the measurements work

**Goodput.** Computed exactly as the assignment specifies, from the difference between
successive cumulative acknowledged-byte counters over the real elapsed sampling time:

```
goodput(t) = (delta tcpi_bytes_acked / delta t) * 8    [bits/s]
```

stored in the CSV as Mbit/s. All statistics come from the live **data** socket, never the
control socket.

**Loss proxy.** TCP exposes no direct per-interval loss count, so the proxy is the growth
of `tcpi_total_retrans` (segments retransmitted) over each interval, with
`tcpi_bytes_retrans` as the same signal in bytes and `retrans_rate` normalising it by
`tcpi_data_segs_out`. Note `tcpi_lost` is *not* differenced — it is the kernel's current
estimate for the in-progress recovery and is non-monotonic, so it is logged as an
instantaneous gauge only.

**`tcp_info` decoding.** `tcp_info.py` decodes the kernel's `struct tcp_info` (layout from
`include/uapi/linux/tcp.h`). The struct only ever grows by appending fields, so the table
describes a known 248-byte prefix: an older kernel returns a shorter buffer and the
missing trailing fields decode as `None` rather than crashing, while a newer kernel's
unknown tail is ignored. Each run records in its JSON how many bytes the kernel actually
wrote (`tcp_info_bytes`).

Measurements so far were taken on kernel **6.18.54.1-microsoft-standard-WSL2**, which
returns **280** bytes. The decode was verified by comparing every field against `ss -ti`
for the same live socket.

**Congestion control algorithm.** Whatever the OS default is, read back from the socket
with `getsockopt(TCP_CONGESTION)` and recorded in every output file. On the kernel above
that is `cubic`.

## Checking it worked

```bash
ls results/
head -1 results/*.csv | tr ',' '\n' | head -20     # column names
```

To confirm the decoder against the kernel, start a run and in a second shell compare:

```bash
ss -tin dst <server-ip>
```

The `cwnd:`, `rtt:`, `bytes_acked:` and `retrans:` values there should track the
corresponding CSV columns.

## Layout

| File | Role |
| --- | --- |
| `main.py` | Entry point |
| `cli.py` | Argument parsing |
| `client.py` | iperf3 test driver and per-interval sampling |
| `protocol.py` | iperf3 wire protocol: states, cookie, length-prefixed JSON |
| `tcp_info.py` | `struct tcp_info` decoder |
| `measurement.py` | Sample/metadata records, CSV + JSON output |
| `plots.py` | All PDF plotting |
| `destinations.py` | Random server selection, retries, multi-destination runs |
| `iperf3-servers.csv` | Server list from https://iperf3serverlist.net/ |
