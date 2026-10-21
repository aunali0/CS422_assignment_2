# Assignment 2 Q3 handoff

The experiment, plots, analysis, and algorithm design are complete for Q3. The proposed algorithm itself is for Assignment 3 to implement and evaluate.

Use **[Q3_REPORT.pdf](Q3_REPORT.pdf)** at the top of this repo. It is five pages: method/results, observations, two required comparison-plot pages, and the algorithm design. The editable version is [Q3_REPORT.md](Q3_REPORT.md).

The earlier 22-page report is supporting material at [detailed-report.pdf](results/q3-test/supporting/detailed-report.pdf). Full measurements, extra plots, and longer analysis stay under results/q3-test/. They do not need to be pasted into the main team report.

## Results

Means across three repetitions; goodput is in Mbit/s and RTT is in ms.

| Destination | Algorithm | Goodput mean | Run standard deviation | RTT mean |
| --- | --- | ---: | ---: | ---: |
| Dallas | CUBIC | 273.96 | 5.63 | 68.73 |
| Dallas | Reno | 281.30 | 2.76 | 73.65 |
| Dallas | BBR | 269.79 | 11.69 | 64.53 |
| Netfiber | CUBIC | 118.08 | 4.16 | 181.90 |
| Netfiber | Reno | 119.07 | 0.89 | 181.67 |
| Netfiber | BBR | 106.59 | 17.37 | 177.39 |
| 96.45.41.167 | CUBIC | 163.12 | 17.51 | 132.58 |
| 96.45.41.167 | Reno | 163.52 | 11.80 | 136.69 |
| 96.45.41.167 | BBR | 147.47 | 6.02 | 150.60 |

Reno had the highest average goodput at all three destinations, but its lead over CUBIC was small on Netfiber and negligible at the IP destination relative to run variation. BBR had lower average RTT on Dallas and Netfiber, with lower throughput, and a transient stall in one run at the IP destination. These are sequential public-path observations, not universal algorithm rankings.

## Checked data

The archive was extracted to results/q3-test. All 49 saved successful runs and 2,940 samples passed identity, timing, counter, goodput, and summary consistency checks. This includes 27 matched runs (1,620 samples) used in the comparison and 22 successful runs from incomplete destination groups. The latter remain on disk but are excluded from matched comparisons. The manifest records 23 failed tests. All three requested destination groups completed.

[validation.json](results/q3-test/validation.json) records the checks, archive checksum, and raw-file checksums. Original CSV/JSON measurements and the manifest remain unchanged. The original shared-axis plotting code could clip later algorithms because it fixed the limits too early; that is corrected in the regenerated plots and covered by a regression test. Use Q3_REPORT.pdf or the regenerated comparison plots when sharing results. The report and plot files can be rebuilt without repeating any network experiments:

```sh
python main.py analyze --manifest results/q3-test/manifest.json
```

The recorded run used Python 3.14.8, matplotlib 3.11.2, pydantic 2.13.5, and Linux kernel 6.18.33.2-microsoft-standard-WSL2. The exact BBR version and whether Docker was used were not recorded. The supplied Dockerfile still needs build/run verification; the report does not claim the submitted measurements were collected in it.

## Team handoff

Merge Q3_REPORT.pdf into the single Assignment 2 report with Q1/Q2, and push the results and analysis files to the team repo. The algorithm pseudocode and thresholds are unchanged from the earlier handoff; the design rationale now incorporates the three-algorithm data. Review the design with whoever owns Assignment 3 before implementing it.
