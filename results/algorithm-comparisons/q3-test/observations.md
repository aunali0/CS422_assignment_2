# Q3 comparison: results and supporting notes

## Experiment

We tested CUBIC, Reno, and BBR at three destinations, with three 60-second runs per
algorithm and one-second sampling: 27 matched runs and 1,620 samples. Each algorithm
was selected before connecting and read back from the data socket.

The host used Linux `6.18.33.2-microsoft-standard-WSL2`, Python 3.14.8, matplotlib
3.11.2, and pydantic 2.13.5. The BBR version and whether Docker was used were not
recorded. `requirements.txt` pins a different dependency environment.

Destinations were shuffled with seed 422. The order rotated across repetitions:

| Destination | Repetition 1 | Repetition 2 | Repetition 3 |
| --- | --- | --- | --- |
| Dallas | BBR, CUBIC, Reno | CUBIC, Reno, BBR | Reno, BBR, CUBIC |
| Netfiber | Reno, BBR, CUBIC | BBR, CUBIC, Reno | CUBIC, Reno, BBR |
| 96.45.41.167 | CUBIC, Reno, BBR | Reno, BBR, CUBIC | BBR, CUBIC, Reno |

Tests ran sequentially with a two-second pause. Dallas was the first complete group
and became the representative. Of eight candidates and 72 tests, 49 tests succeeded
and 23 failed. Five destination groups were incomplete. Their 22 successful runs
remain saved but are excluded from comparisons. All three requested groups completed.

## What the numbers mean

Goodput measures acknowledged bytes over the actual elapsed time, in Mbit/s. Each
run's rate is total acknowledged bytes divided by total measured time. The table
averages three run rates; ± shows their sample standard deviation, or variation
between runs. RTT is the average sampled smoothed RTT, in milliseconds.

Congestion window (`cwnd`) limits outstanding segments; it is not the actual amount
of data in flight. Retransmissions count segments sent again and provide a loss
signal. They do not directly measure packet-loss probability.

Per-test summaries also contain minimum, median, arithmetic mean, and P95 sampled
goodput. P95 uses linear interpolation at position `(n - 1) * 0.95` after sorting.
All samples, including startup and stalls, are retained.

## Results

| Destination | Algorithm | Goodput mean ± SD (Mbit/s) | Mean RTT (ms) | Total retransmissions |
| --- | --- | ---: | ---: | ---: |
| Dallas | CUBIC | 273.96 ± 5.63 | 68.73 | 224 |
| Dallas | Reno | 281.30 ± 2.76 | 73.65 | 444 |
| Dallas | BBR | 269.79 ± 11.69 | 64.53 | 196 |
| Netfiber | CUBIC | 118.08 ± 4.16 | 181.90 | 23 |
| Netfiber | Reno | 119.07 ± 0.89 | 181.67 | 41 |
| Netfiber | BBR | 106.59 ± 17.37 | 177.39 | 398 |
| 96.45.41.167 | CUBIC | 163.12 ± 17.51 | 132.58 | 120 |
| 96.45.41.167 | Reno | 163.52 ± 11.80 | 136.69 | 11 |
| 96.45.41.167 | BBR | 147.47 ± 6.02 | 150.60 | 541 |

Dallas is `dal.speedtest.clouvider.net:5200`; Netfiber is
`speed.netfiber.net.il:5201`; the IP destination uses port 30001.

Reno had the highest mean throughput at all three destinations. BBR had lower mean
RTT at Dallas and Netfiber. Reno and CUBIC were close at Netfiber and almost tied at
the IP destination. These differences should be considered alongside run variation.

At Dallas, Reno's median cwnd increased from 1,982 to 7,854 segments across runs,
while goodput stayed around 279–284 Mbit/s. Allowing more outstanding data did not
produce a similar throughput increase. Minimum RTT was about 29–32 ms, below the
sampled means. Queueing or other variable delay may explain some of that gap.

At Netfiber, minimum RTT was around 170–174 ms. BBR's third run delivered only
86.57 Mbit/s and recorded 396 retransmissions, versus 115.56 and 117.63 Mbit/s with
two and zero retransmissions in the first two runs. Much of the slowdown occurred
without a large RTT increase. At the IP destination, BBR had one zero-goodput
interval around 50 seconds, with RTT reaching 1,559.64 ms. Both transfers completed.

## Interpretation and limitations

Reno increases its window additively during congestion avoidance [1]. CUBIC uses a
cubic growth function intended for fast, long-distance paths [2]. BBR estimates
rate and baseline RTT [3]. We did not observe a CUBIC or BBR throughput win; the
measurements do not cover every condition where those algorithms may help.

Bandwidth-delay product is bandwidth times propagation RTT. It estimates how much
data must be in flight to fill the path. We compared cwnd times segment size with
achieved goodput times minimum RTT. Dallas's third Reno run had about 11.37 MB of
window allowance versus a 1.09 MB rate-times-RTT estimate. This suggests another
limit on delivery, but does not identify whether it was the receiver, server,
pacing, or path. Using achieved rate cannot independently establish path capacity.

The tests were sequential on changing public paths. Rotating order helps reduce
order bias but cannot hold traffic or routes constant. Three repetitions and
one-second samples limit what can be concluded. Scatter plots associate values
measured together; they do not establish causes. Single-flow tests do not measure
fairness, and retaining only complete groups favors reliable destinations.

## Design and reproduction

[Q3_DESIGN.md](../../../Q3_DESIGN.md) is the selected Assignment 2 controller
proposal. It uses loss for recovery, RTT to guide growth, and goodput to decide
whether high delay warrants a reduction. It has not been implemented or evaluated;
the baseline data motivate the signals but do not validate its thresholds.

The manifest records settings, environment, exact order, and statuses. `tcp-traces/`
contains raw CSV/JSON measurements and individual plots; `reports/` contains summary
tables and reports; `plots/` contains combined figures. `experiment.log` records
failures, and `validation.json` records the measurement and summary checks.

[Q3_RUN.md](../../../Q3_RUN.md) gives collection, Docker, and offline-analysis commands.
[Q3_REPORT.md](../../../Q3_REPORT.md) is the main report source; the existing PDF still
contains its earlier wording. The saved experiment is unchanged; its runs do not evaluate the custom controller.

Repository: https://github.com/aunali0/CS422_assignment_2 . Relevant code is
`client.py:data_connection`, `comparison.py:run_comparison`,
`comparison_plots.py:run_statistics/plot_comparison`, and `reviewed_report.py`.
AI assistance helped with code, plots, consistency checks, and wording; a teammate
collected the measurements on Linux/WSL2.

[1] https://www.rfc-editor.org/rfc/rfc5681.html#section-3.1
[2] https://www.rfc-editor.org/rfc/rfc9438.html
[3] https://github.com/google/bbr/blob/master/Documentation/bbr-faq.md
