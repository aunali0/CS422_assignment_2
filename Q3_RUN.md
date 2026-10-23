# Running the algorithm comparison

The saved Q3 experiment compares CUBIC, Reno, and BBR at three destinations, with
three 60-second runs per algorithm and one-second sampling. All 27 matched runs
completed. Data and outputs are under `results/algorithm-comparisons/q3-test/`.

Read [Q3_REPORT.md](Q3_REPORT.md) for the main report and
[observations.md](results/algorithm-comparisons/q3-test/observations.md) for the
results table and supporting notes. Existing PDFs contain the earlier report text;
these Markdown sources have since been simplified.

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
docker run --rm --network host -v "$PWD/results:/results" cs422-a2 compare -s iperf3-servers.csv -c 3 -t 60 -g 1 -r 3 --seed 422 --run-id q3-docker -o /results
```

The image uses `ubuntu:24.04` and Python 3.12. Containers share the host kernel,
so the host must support the requested algorithms. The saved experiment used WSL2
kernel `6.18.33.2-microsoft-standard-WSL2`, Python 3.14.8, matplotlib 3.11.2, and
pydantic 2.13.5. `requirements.txt` pins a different dependency environment. The
Docker pipeline remains unverified, and the saved manifest does not establish
whether Docker was used or identify the BBR version.

## Outputs and offline analysis

Each experiment is under `results/algorithm-comparisons/<run-id>/`:

| Location | Contents |
| --- | --- |
| `manifest.json` | Settings, host environment, order, status, and actual algorithms |
| `servers-input.csv`, `experiment.log` | Input snapshot and failure details |
| `tcp-traces/<test>/` | Raw samples, metadata with units, and individual plots |
| `reports/per-test-statistics.csv` | Goodput, RTT, window, and retransmission statistics for every successful run |
| `reports/destination-algorithm-statistics.csv` | Means and variation across matched repetitions |
| `plots/algorithm-metrics-*.pdf` | Representative destination, all algorithms, common axis scales |
| `reports/algorithm-comparison-report.*` | Generated detailed report and plots |
| `reports/reviewed-algorithm-comparison.pdf` | Reviewed report, generated from `Q3_REPORT.md` when observations are present |

The first complete destination is the representative; it is not selected for high
throughput. To rebuild outputs from saved measurements without contacting servers:

```sh
python main.py analyze --manifest results/algorithm-comparisons/q3-test/manifest.json
```

This command overwrites the generated reports and plots. The current Markdown edits
have not been rendered into the existing PDFs.

## Assignment 3 and submission

[Q3_DESIGN.md](Q3_DESIGN.md) is the selected Assignment 2 controller proposal and
starting point for Assignment 3. The report sources and generator use this design.
It has not been implemented or evaluated. Document any further implementation
changes from the selected Assignment 2 design.

Once a custom controller is implemented and loaded, collect four-algorithm tests:

```sh
python main.py compare -s iperf3-servers.csv -c 3 -t 10 -g 0.2 -r 3 --algorithms cubic reno bbr CUSTOM_NAME --run-id a3-final -o results
```

The rotating order still applies; three repetitions cannot fully balance four order
positions. Record the actual order in the report. Review report wording and layout
for four algorithms before submission.

For Assignment 2, combine Q1/Q2 and Q3 into one PDF with the plots, interpretations,
repository and code links, reproduction instructions, and a brief AI acknowledgement.
The saved measurements have been checked against their summaries; see `validation.json`.
Mocked tests cover algorithm selection and experiment handling. The test suite also
includes offline report generation and writes temporary outputs:

```sh
python -m unittest discover -s tests -v
```
