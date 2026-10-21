# Assignment 2 Q3

Implemented: algorithm selection before data-socket connect, repeated matched experiments, raw CSV/JSON, common-scale comparison plots, summary tables, a generated report, and algorithm pseudocode in Q3_DESIGN.md.

The full comparison has now been run by a teammate on Linux/WSL2 and imported from res.zip. The checked dataset is results/q3-test: three destinations, three algorithms, three repetitions, 60 seconds per run, and one-second sampling. All 27 matched runs completed. See [Q3_RESULTS.md](Q3_RESULTS.md) for the handoff and [the five-page Q3 report](Q3_REPORT.pdf). Q3_REPORT.pdf is at the top of the repo and includes implementation links, the two required plot pages, analysis, and the algorithm design. The longer report is supporting material under results/q3-test/supporting/. Merge it with the team's Q1/Q2 report for the single assignment submission.

## Run on Linux or WSL2

Python 3.12 or newer is required. The Linux kernel must support cubic, reno, and bbr. The command checks all requested algorithms before contacting servers and fails if any is unavailable. It never silently substitutes an algorithm. The existing uv.lock required Python 3.14.7 and was removed when lowering the supported minimum to 3.12; requirements.txt pins the two direct dependencies used for local verification.

```sh
cd CS422_assignment_2
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python main.py compare -s iperf3-servers.csv -c 10 -t 60 -g 1 -r 3 --seed 422 --run-id q3-final -o results
```

Ten destinations, three algorithms, and three repetitions take at least 90 minutes at 60 seconds each. Failures and replacements add time. A smaller configurable destination count is allowed by the assignment; `-c 3` takes at least 27 minutes. Use a fresh run ID for another experiment. For a smoke test, use a small server-list CSV with IP/HOST and PORT columns, `-c 1 -t 10 -r 1` and a separate run ID. Keep smoke tests separate from the final results.

If BBR is unavailable, the host owner may need to enable CONFIG_TCP_CONG_BBR or load the tcp_bbr module. The program does not change kernel configuration. Containers share the host kernel; installing packages in the container cannot add a missing host congestion-control algorithm. Record relevant host setup in the final report.

## Docker on the supported Linux host

```sh
docker build -t cs422-a2 .
mkdir -p results
docker run --rm --network host -v "$PWD/results:/results" cs422-a2 compare -s iperf3-servers.csv -c 10 -t 60 -g 1 -r 3 --seed 422 --run-id q3-final -o /results
```

The Dockerfile uses ubuntu:24.04 and Python 3.12. No privileged container is needed for selecting an available TCP algorithm. Docker Desktop on macOS is not the assignment's specified Linux/WSL2 execution environment. The image build could not be tested locally because the Docker daemon is stopped.

## Files produced

Everything is under results/q3-final/:

- manifest.json: kernel, Python and library versions, configuration, candidate selection, actual algorithms, exact execution order, timestamps, statuses, and complete destination groups.
- servers-input.csv and experiment.log: input list and diagnostics.
- Per-test CSV/JSON: raw measurements, actual algorithm, kernel, units, and run ID. Successful runs are saved immediately.
- per-run-summary.csv: goodput min/median/mean/P95, duration-weighted goodput, RTT mean/P95, cwnd, an observed-rate BDP proxy, and retransmissions.
- aggregate-summary.csv: mean, sample standard deviation, and range across repetitions for matched destination/algorithm groups.
- comparison-timeseries.pdf and comparison-scatter.pdf: all algorithms on the same representative destination, including repetitions, with common scales for each metric.
- comparison-report.pdf and comparison-report.md: method, measured summaries, interpretation, limitations, and AI acknowledgement. The PDF also includes the Q3(b) design and the comparison plots.
- Individual per-test plots and goodput panels for every complete destination in the report.

A failed candidate is replaced as a whole after its planned tests finish. Partial successful data are retained and marked as unmatched, and excluded from aggregate comparisons. The maximum candidate count is `count * attempts`. A nonzero exit status reports a destination shortfall; inspect the manifest and log. An interrupted run retains measurements and running/pending statuses; use a fresh run ID to rerun, or analyze what was saved. It does not resume incomplete runs automatically.

The initial algorithm order is seeded and shuffled, then rotated across repetitions and destinations. With three repetitions each algorithm appears once in each order position per destination. With other repetition counts balancing may be incomplete. The first destination that completes every test is the representative, avoiding selection by which algorithm won.

Rebuild the submitted plots and reports without network traffic, including on macOS (observations.md in the run directory supplies the reviewed analysis):

```sh
python main.py analyze --manifest results/q3-test/manifest.json
```

## Handoff and submission

Share Q3_DESIGN.md with whoever implements Assignment 3 before they choose the kernel/eBPF implementation. The design is a proposal, not an implemented kernel algorithm. It explicitly states its state, thresholds, RTT/throughput/loss updates, fairness expectations, and limitations. Revisit its thresholds after collecting all three baselines.

For Assignment 3 Option 1, after the custom algorithm has been implemented and loaded, the same runner can collect four-algorithm 10-second experiments:

```sh
python main.py compare -s iperf3-servers.csv -c 3 -t 10 -g 0.2 -r 3 --algorithms cubic reno bbr CUSTOM_NAME --run-id a3-final -o results
```

Review measured differences relative to run variability. Add any trace-specific anomalies and justified changes to the proposed design. Merge the Q3 report into the shared Assignment 2 report, include the repository URL and links to data_connection in client.py, run_comparison in comparison.py, and plot_comparison/build_report in comparison_plots.py, and embed the plots. The final Brightspace submission is one combined PDF. AI use is acknowledged once in the report, as the assignment requests.

## Verification

```sh
python -m unittest discover -s tests -v
```

Tests check pre-connect algorithm selection, rejection of unavailable/mismatched algorithms, whole-group replacement, balanced order, acknowledged-byte goodput, and offline report generation using existing measurements. Tests use mocked network operations; they do not demonstrate live iperf3 compatibility on Linux. The imported live three-algorithm results passed the checks recorded in results/q3-test/validation.json. The Docker build remains unverified; the supplied run manifest does not record whether Docker was used.
