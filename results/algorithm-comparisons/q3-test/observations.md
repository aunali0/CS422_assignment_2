# Assignment 2 Q3: Algorithm comparison and design

## Experiment

We compared CUBIC, Reno, and BBR at three destinations, with three runs per algorithm and destination. Every run lasted 60 seconds and sampled the data socket once per second. This gives 27 matched runs and 1,620 samples. The run identifier is q3-test. Despite the name, these are full 60-second experiments, not short smoke tests. Each algorithm was selected before connecting the data socket, then read back from that socket and saved with the measurements.

The host ran Linux 6.18.33.2-microsoft-standard-WSL2, Python 3.14.8, matplotlib 3.11.2, and pydantic 2.13.5. The manifest confirms that the kernel accepted cubic, reno, and bbr. It does not identify the BBR implementation version or whether the run used Docker, so we do not assume either. The supplied Dockerfile uses ubuntu:24.04; reproducing the kernel behavior also requires a supported Linux/WSL2 host with the algorithms available.

We shuffled the server list with seed 422 and rotated the initial algorithm order across repetitions. Dallas used BBR/CUBIC/Reno, CUBIC/Reno/BBR, then Reno/BBR/CUBIC. Netfiber used Reno/BBR/CUBIC, BBR/CUBIC/Reno, then CUBIC/Reno/BBR. The IP destination used CUBIC/Reno/BBR, Reno/BBR/CUBIC, then BBR/CUBIC/Reno. Thus each algorithm occupied each position once at each retained destination. Individual tests were sequential, with a configured two-second pause between them. The representative destination is dal.speedtest.clouvider.net:5200, the first complete group; it was chosen without comparing throughput.

Eight candidate destinations were attempted. Of 72 tests, 49 succeeded and 23 failed. The failures included server rejections, timeouts, broken pipes, and an unreachable network. Five destinations lacked at least one successful repetition. Their 22 successful runs are retained as partial data, but are excluded from the matched comparisons below. All three requested destination groups completed. The exact execution order, timestamps, algorithms, and failures are in manifest.json and experiment.log.

## Measurement and summary method

Goodput is the increase in the data socket's cumulative acknowledged-byte count divided by the actual sampling interval, multiplied by eight. We report Mbit/s. A run's duration-weighted goodput is total acknowledged bytes divided by total sampled seconds. Each reported algorithm mean gives equal weight to its three run means. The variability shown with those means is the sample standard deviation across the three runs, not a confidence interval.

RTT is Linux TCP_INFO's smoothed RTT in milliseconds. A run's mean RTT averages its 60 samples; the algorithm summary averages the three run means. Congestion window is snd_cwnd in segments. Its byte budget is snd_cwnd times snd_mss; it is a limit on outstanding data, not a direct measurement of bytes currently in flight. Retransmissions are interval increases in total_retrans and are a loss proxy, not an independent measurement of packet-loss probability.

Per-run summary tables include minimum, median, arithmetic mean, and P95 sampled goodput for every destination and algorithm. P95 is linearly interpolated at index (n - 1) times 0.95 in the sorted samples. The CSV also includes duration-weighted goodput, mean/P95 RTT, window statistics, and an observed-rate bandwidth-delay-product proxy. Startup and low-throughput intervals remain in every summary; no outliers were removed.

## Dallas: throughput and RTT tradeoff

At dal.speedtest.clouvider.net:5200, mean goodput was 281.30 Mbit/s for Reno, 273.96 for CUBIC, and 269.79 for BBR. The corresponding across-run standard deviations were 2.76, 5.63, and 11.69 Mbit/s. Reno's mean was 2.7% above CUBIC and 4.3% above BBR. BBR had the lowest mean RTT: 64.53 ms, versus CUBIC's 68.73 and Reno's 73.65 ms. That is a throughput/latency tradeoff in these measurements, not a universal ranking. With only three runs and overlapping throughput ranges, the ordering needs more evidence before being treated as a consistent advantage.

The representative plots show different window trajectories without proportional changes in delivered rate. Reno's median cwnd increased across repetitions from 1,982 to 4,657 to 7,854 segments, while its run goodputs stayed between 279.14 and 284.41 Mbit/s. In its third run, median cwnd times MSS was about 11.37 MB, while achieved rate times minimum filtered RTT was about 1.09 MB. A larger window budget therefore did not translate into proportionally higher goodput. Another limit, such as the receiver, server, or path capacity, may dominate; the trace does not identify which one.

Minimum filtered RTTs were around 29-32 ms, while sampled mean RTTs were roughly 59-75 ms across runs. The excess is consistent with queueing or other variable delay, including reverse-path delay. We cannot assign all of it to a forward-path queue. Across the three runs, Reno recorded 444 retransmitted segments, CUBIC 224, and BBR 196. Reno still delivered the highest mean goodput, so a larger retransmission count alone does not determine the throughput ordering.

## Netfiber: long RTT and a variable BBR run

At speed.netfiber.net.il:5201, minimum filtered RTTs were around 170-174 ms. Reno and CUBIC achieved similar mean rates: 119.07 and 118.08 Mbit/s, with standard deviations of 0.89 and 4.16 Mbit/s. Reno's advantage was only 0.8%, smaller than the observed CUBIC run variation. Their mean RTTs were also similar, at 181.67 and 181.90 ms.

BBR averaged 106.59 Mbit/s with a much larger 17.37 Mbit/s standard deviation, while its mean RTT was slightly lower at 177.39 ms. Its first two runs delivered 115.56 and 117.63 Mbit/s with two and zero retransmitted segments. The third delivered 86.57 Mbit/s with 396 retransmissions, accounting for almost all of BBR's 398 retransmissions at this destination. At about 17 seconds in that run, goodput was 33.16 Mbit/s with RTT 176.11 ms, close to the path's baseline. This associates the low-goodput period with retransmission activity and window changes without evidence of sustained RTT inflation. It does not prove whether random loss, cross-traffic, or another condition caused it.

The median window sizes across all samples were 5,820 segments for Reno and 3,964 for CUBIC, despite their similar rates. As in Dallas, extra permitted in-flight data was not sufficient to raise useful throughput. This path is a high-RTT regime where Reno and CUBIC performed similarly in our runs; it provides no measured evidence that CUBIC's large-bandwidth-delay scaling produced an advantage here.

## IP destination: similar Reno/CUBIC rates and transient stalls

At 96.45.41.167:30001, Reno and CUBIC averaged 163.52 and 163.12 Mbit/s. Their standard deviations were 11.80 and 17.51 Mbit/s, making the 0.41 Mbit/s difference negligible relative to run variability. CUBIC had a slightly lower mean RTT, 132.58 ms versus Reno's 136.69 ms, but the respective RTT standard deviations were both about 13.3 ms.

BBR averaged 147.47 Mbit/s and 150.60 ms RTT. Its RTT standard deviation was 38.60 ms, driven partly by a 192.79 ms mean in its first run. At about 50 seconds in that run, acknowledged goodput was zero for one interval and smoothed RTT reached 1,559.64 ms; retransmissions also increased. This is a short stall within a completed transfer, not a failed experiment. BBR's three runs recorded 541 retransmitted segments in total, versus CUBIC's 120 and Reno's 11.

The median window across samples was 5,749 segments for BBR, versus 3,965 for CUBIC and 3,984 for Reno. Here the larger BBR window coexisted with lower mean goodput and more variable RTT. That combination supports using throughput and loss signals alongside window size. It does not establish that BBR caused the path conditions: the algorithms were tested at different times, and their minimum RTTs also differed.

## Operating regimes and limits of the comparison

Reno increases its congestion window by approximately one segment per RTT during congestion avoidance [1]. CUBIC uses a cubic growth function intended to scale on fast, long-distance paths [2]. BBR uses a delivery-rate and RTT model to guide sending [3]. Those mechanisms explain what each algorithm tries to do; they do not override the measured results or identify the cause of a public-path anomaly.

In this dataset, Reno had the highest mean goodput at each destination. Its advantage over CUBIC was small on Netfiber and negligible on the IP destination. BBR had the lowest mean RTT on Dallas and Netfiber, with lower throughput there, and did not maintain that RTT advantage on the IP destination. No sampled destination establishes a CUBIC throughput win or a BBR throughput win. CUBIC's expected advantage on a controlled large-bandwidth-delay bottleneck, or BBR's possible advantage under particular loss/queue conditions, would require additional controlled tests rather than being inferred from these traces.

For a window-limited sender, rate is approximately cwnd times MSS divided by RTT. Bandwidth-delay product is bottleneck bandwidth times propagation RTT. Our recorded proxy substitutes achieved goodput and minimum filtered RTT, so it is not an independent estimate of bottleneck capacity. On the third Dallas Reno run, the window budget was about 10.4 times that proxy; this demonstrates that window budget alone cannot explain the rate, but does not measure queue occupancy. Linux's receive-window, pacing, recovery, and application limits can impose tighter constraints than cwnd.

The scatter plots pair instantaneous window/RTT readings with goodput and retransmissions over the preceding interval. Recovery can affect later intervals, so scatter associations are not causal estimates. The one-second sampling can also miss shorter congestion events. Differences in Internet cross-traffic, routes, reverse-path traffic, server limits, and host load remain uncontrolled. Rotated order reduces position bias but cannot make sequential tests simultaneous. Selecting only complete server groups favors reliable destinations. Three repetitions provide limited evidence about variability, and these were single-flow tests, not fairness experiments.

## Algorithm design

Q3_DESIGN.md supplies the state, pseudocode, initial parameters, and fairness/stability discussion for our proposed algorithm. The attached design uses RTT, acknowledged throughput, and recovery/loss events together. The baseline results motivate its decision to stop routine window growth when a larger budget is not improving delivery, to distinguish sustained RTT inflation from loss activity, and to keep occasional probes when an observed rate estimate may be too low. Its thresholds remain hypotheses; none of the measurements evaluate the proposed algorithm itself. The next assignment must implement and test it.

## Reproduction and implementation links

From the Assignment 2 directory, install requirements.txt and run: python main.py compare -s iperf3-servers.csv -c 3 -t 60 -g 1 -r 3 --seed 422 --run-id q3-test -o results. Use a fresh run ID if that directory already exists. This reproduces the experiment procedure; changing public Internet conditions will change results. The recorded Python and library versions above describe the submitted run; requirements.txt pins a different locally tested environment, so it should not be presented as the exact measured user-space environment.

The input snapshot is results/algorithm-comparisons/q3-test/servers-input.csv. Raw per-test CSV/JSON and individual plots are under tcp-traces/<test>/; summary tables and reports are under reports/; combined plots are under plots/. The measurements include actual algorithms, run identifiers, units, and the kernel version, while experiment.log records failures. validation.json records an independent consistency check of the imported archive. Rebuild the plots and reports offline with: python main.py analyze --manifest results/algorithm-comparisons/q3-test/manifest.json. The concise five-page Q3 report is results/algorithm-comparisons/q3-test/reports/reviewed-algorithm-comparison.pdf. Q3_RUN.md documents the Docker command and remaining team submission steps.

Repository: https://github.com/aunali0/CS422_assignment_2 . Socket selection before connect: https://github.com/aunali0/CS422_assignment_2/blob/4389022/client.py#L53 . Experiment ordering and persistence: https://github.com/aunali0/CS422_assignment_2/blob/4389022/comparison.py#L51 . Measurement and common-scale plots: https://github.com/aunali0/CS422_assignment_2/blob/4389022/comparison_plots.py#L22 and https://github.com/aunali0/CS422_assignment_2/blob/4389022/comparison_plots.py#L74 . These links identify the experiment implementation; reviewed_report.py generates the final Q3 PDF from these observations, the saved results, and the design.

## References and assistance

[1] RFC 5681, TCP Congestion Control, section 3.1: https://www.rfc-editor.org/rfc/rfc5681.html#section-3.1

[2] RFC 9438, CUBIC for Fast and Long-Distance Networks: https://www.rfc-editor.org/rfc/rfc9438.html

[3] Google's BBR FAQ, model overview: https://github.com/google/bbr/blob/master/Documentation/bbr-faq.md . The saved kernel algorithm name is bbr; its implementation version was not recorded.

AI assistance was used for experiment automation, plotting, consistency checks, and drafting the design and analysis. The measurements were collected on a team member's Linux/WSL2 machine. The proposed algorithm has not yet been evaluated.
