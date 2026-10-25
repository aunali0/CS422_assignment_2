# Running the algorithm comparison

The saved Q3 experiment compares CUBIC, Reno, and BBR at three destinations, with
three 60-second runs per algorithm and one-second sampling. All 27 matched runs
completed. Data and outputs are under `results/algorithm-comparisons/q3-test/`.

The results, interpretation, and controller design are in the report
(`python main.py report`, written from [REPORT.md](REPORT.md)).

## Setup and collection

Use Linux or WSL2 with Python 3.12 or newer. Follow the installation commands in
[README.md](README.md). The host kernel must provide `cubic`, `reno`, and `bbr`.
The client checks each algorithm before contacting servers and reports missing
support. The host administrator may need to load `tcp_bbr` for BBR.

```sh
python main.py compare -s iperf3-servers.csv -c 3 -t 60 -g 1 -r 3 --seed 422 --run-id q3-repeat -o results
```

`-c` selects the destination count, `-t` the duration, `-g` the sampling interval,
and `-r` the repetitions. Three destinations take at least 27 minutes of transfer
time, plus pauses and retries. Use a fresh run ID for every experiment. The server
CSV needs `IP/HOST` and `PORT` columns.

All algorithms use the same destinations and settings. The runner shuffles the
initial order, then rotates it by repetition and destination. With three algorithms
and three repetitions, each algorithm occupies each position once per destination.
The manifest records the exact order. A two-second pause separates tests.

A destination is included in comparisons only if every algorithm and repetition
succeeds. Failed groups are replaced within `count * attempts` candidates. Successful
partial runs remain saved but are excluded from aggregate comparisons. Shortfalls
produce a nonzero exit status. Interrupted runs can be analyzed but are not resumed.

For a shorter check, use `-c 1 -t 10 -r 1` with a separate run ID.

## Docker

```sh
docker build -t cs422-a2 .
mkdir -p results
docker run --rm --network host --cap-add NET_ADMIN -v "$PWD/results:/results" cs422-a2 compare -s iperf3-servers.csv -c 3 -t 60 -g 1 -r 3 --seed 422 --run-id q3-docker -o /results
```

The image uses `ubuntu:24.04` and Python 3.12 with the same matplotlib (3.11.2) and
pydantic (2.13.5) versions as the saved experiment. Containers share the host kernel,
so the host must support the requested algorithms (`sudo modprobe tcp_bbr`). Selecting
an algorithm outside `net.ipv4.tcp_allowed_congestion_control` requires `CAP_NET_ADMIN`,
hence `--cap-add NET_ADMIN`. The saved experiment used WSL2
kernel `6.18.33.2-microsoft-standard-WSL2` and Python 3.14.8. The saved manifest does
not establish whether Docker was used or identify the BBR version.

## Outputs and offline analysis

Each experiment is under `results/algorithm-comparisons/<run-id>/`:

| Location | Contents |
| --- | --- |
| `manifest.json` | Settings, host environment, order, status, and actual algorithms |
| `servers-input.csv`, `experiment.log` | Input snapshot and failure details |
| `tcp-traces/<test>/` | Raw samples, metadata with units, and individual plots |
| `reports/per-test-statistics.csv` | Goodput, RTT, window, and retransmission statistics for every successful run |
| `reports/destination-algorithm-statistics.csv` | Means and variation across matched repetitions |
| `plots/destination-goodput-over-time.pdf`, `reports/destination-goodput-statistics.pdf` | Q1 goodput plot and min/median/mean/P95 table for the complete destinations |
| `plots/algorithm-metrics-*.pdf` | Representative destination, all algorithms, common axis scales |
| `plots/destinations/<destination>/` | The same comparison for every complete destination |
| `reports/algorithm-comparison-report.*` | Generated detailed report and plots |

The first complete destination is the representative; it is not selected for high
throughput. To rebuild outputs from saved measurements without contacting servers:

```sh
python main.py analyze results/algorithm-comparisons/q3-test
```

This command overwrites the generated reports and plots.

## Submission

For Assignment 2, combine Q1/Q2 and Q3 into one PDF with the plots, interpretations,
repository and code links, reproduction instructions, and a brief AI acknowledgement.
