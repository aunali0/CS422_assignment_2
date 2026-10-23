# CS 422 Assignment 2 — Python iperf3 client

This client implements the iperf3 socket protocol directly. It opens control and
data connections, exchanges test parameters, sends data for a chosen duration,
and ends the test. It does not invoke the iperf3 binary.

During transfer it reads TCP statistics from the data socket and records goodput,
congestion window, RTT, and retransmissions. The commands produce raw measurements,
PDF plots, and summary tables.

## Start here

- [Q3_REPORT.md](Q3_REPORT.md): main comparison report, with simpler explanations.
- [Q3_RUN.md](Q3_RUN.md): comparison, Docker, and reproduction commands.
- [Q3_DESIGN.md](Q3_DESIGN.md): selected controller proposal; not implemented or tested.
- [Saved results](results/algorithm-comparisons/q3-test/): three destinations, three algorithms, three repetitions.
- [Existing report PDF](results/algorithm-comparisons/q3-test/reports/reviewed-algorithm-comparison.pdf): earlier report text; the Markdown sources have since been simplified.

## Install

Run experiments on Linux or Windows with WSL2. Python 3.12 or newer is required.
Native Windows is not supported by the client's Unix imports and Linux TCP decoder.
Offline analysis can also run on macOS.

```sh
cd /path/to/CS422_assignment_2
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

Use `python` from the activated environment for the examples. `uv run` is another
option; it uses the dependencies in `pyproject.toml`, which differ from the pinned
`requirements.txt` environment. Exact versions for the saved Q3 run are recorded
in its manifest and [Q3_RUN.md](Q3_RUN.md).

## Commands

Test one server for 15 seconds, sampling every half-second:

```sh
python main.py test -s 185.180.12.40 -p 5201 -t 15 -g 0.5
```

Test ten random destinations for 60 seconds each:

```sh
python main.py destinations -s iperf3-servers.csv -c 10 -a 3 -t 60 -g 1
```

Busy, unreachable, or rejecting servers are replaced within the attempt limit.
The command reports how many destinations succeeded. The server list comes from
[iperf3serverlist.net](https://iperf3serverlist.net/). The CSV has `IP/HOST` and
`PORT` columns; for a port range, the client uses its first port.

Compare CUBIC, Reno, and BBR with three repetitions per destination:

```sh
python main.py compare -s iperf3-servers.csv -c 3 -t 60 -g 1 -r 3 --seed 422 --run-id q3-repeat
```

Analyze existing measurements without contacting servers:

```sh
python main.py analyze --manifest results/algorithm-comparisons/q3-test/manifest.json
```

Analysis overwrites generated reports and plots. See [Q3_RUN.md](Q3_RUN.md) for
Docker commands and how failed comparison groups are handled.

| Option | Default | Meaning |
| --- | --- | --- |
| `-t, --time` | 60 s | Duration of each transfer |
| `-g, --goodput-interval` | 1 s | Goodput and TCP sampling interval |
| `-i, --print-interval` | 5 s | Progress-print interval |
| `-c, --count` | 10 | Destination count (`destinations`, `compare`) |
| `-a, --attempts` | 3 | Replacement limit; comparison tries at most `count * attempts` candidates |
| `-r, --repetitions` | 3 | Runs per algorithm and destination (`compare`) |
| `--algorithm NAME` | OS default | Algorithm for `test` or `destinations` |
| `--algorithms NAME ...` | cubic reno bbr | Algorithms for `compare` |
| `-o, --out-dir` | results | Base output directory |
| `--run-id` | UTC timestamp | Experiment identifier; use a fresh ID |
| `--connect-timeout` | 5 s | Connection timeout |
| `--control-timeout` | 3 s | Control-message timeout |
| `--data-timeout` | 3 s | Data-socket idle timeout |

For `test`, `-s` is the host and `-p` is the port (default 5201). For the other
collection commands, `-s` is the server-list CSV. Use `python main.py COMMAND --help`
for all options.

## Results

Each experiment has a category and run directory:

| Command | Directory under `results/` |
| --- | --- |
| `test` | `single-server-tests/<run-id>/` |
| `destinations` | `destination-tests/<run-id>/` |
| `compare` | `algorithm-comparisons/<run-id>/` |

Within it:

| Location | Contents |
| --- | --- |
| `tcp-traces/<test>/tcp-samples.csv` | Goodput, sample intervals, counter changes, and decoded TCP fields |
| `tcp-traces/<test>/test-metadata.json` | Destination, actual algorithm, kernel, settings, and column units |
| `tcp-traces/<test>/tcp-metrics-over-time.pdf` | Window, RTT, retransmissions, and goodput over time |
| `tcp-traces/<test>/tcp-metrics-vs-goodput.pdf` | Window, RTT, and retransmissions plotted against goodput |
| `plots/destination-goodput-over-time.pdf` | Destination goodput plots (`destinations`) |
| `reports/destination-goodput-statistics.pdf` | Minimum, median, mean, and P95 goodput (`destinations`) |
| `plots/algorithm-metrics-*.pdf` | Algorithms compared at the representative destination |
| `reports/per-test-statistics.csv` | Statistics for every successful comparison test |
| `reports/destination-algorithm-statistics.csv` | Statistics across matched repetitions |
| `reports/algorithm-comparison-report.*` | Detailed comparison report and plots |
| `reports/reviewed-algorithm-comparison.pdf` | Reviewed Q3 report, when observations are available |

Test folder names identify the run and destination; comparison names also include
the algorithm and repetition. `destinations` produces TCP plots for the server
with the highest median goodput; this is a selection rule, not proof that the
server was free of rate limits. `compare` uses the first complete destination.

The October 5 goodput PDFs remain under `results/destination-tests/20261005/`.
Their raw samples are not available in this repository.

## Measurements

Goodput uses the difference between consecutive acknowledged-byte counters and
the actual elapsed time:

```text
goodput = acknowledged_bytes_change / elapsed_seconds * 8    [bits/s]
```

The CSV stores Mbit/s. All readings come from the live data socket.

The loss signal is the increase in `tcpi_total_retrans`, counted in retransmitted
segments. It can indicate loss, but also includes unnecessary retransmissions.
`tcpi_lost` is an instantaneous estimate and is not differenced.

`tcp_info.py` decodes a known 248-byte prefix of Linux's `struct tcp_info`. Missing
trailing fields become `None`; unknown newer fields are ignored. Metadata records
the number of bytes returned. The earlier Q2 traces used kernel 6.18.54.1, and the
Q3 comparison used 6.18.33.2, both WSL2 kernels returning 280 bytes. Each test records
the algorithm read back from its socket; the default can differ between machines.

To compare a live socket with the recorded fields, run this in a second terminal:

```sh
ss -tin dst <server-ip>
```

Check `cwnd`, `rtt`, `bytes_acked`, and retransmissions against nearby CSV samples.

## Code

| File | Responsibility |
| --- | --- |
| `main.py`, `cli.py` | Entry point and arguments |
| `client.py`, `protocol.py` | Transfer loop and iperf3 message exchange |
| `tcp_info.py`, `measurement.py` | TCP decoding, sample records, and persistence |
| `destinations.py` | Random destinations and replacement attempts |
| `comparison.py` | Repetitions, algorithm selection, and experiment manifest |
| `plots.py`, `comparison_plots.py`, `reviewed_report.py` | Plots, statistics, and reports |
