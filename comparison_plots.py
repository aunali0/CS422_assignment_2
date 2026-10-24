import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import fmean, median, stdev
from textwrap import wrap

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from plots import Run, save_run_plots, style_axes, values


def percentile(data, fraction):
    ordered = sorted(data)
    position = (len(ordered) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def run_statistics(test, run: Run):
    meta, samples = run
    goodput = [s.goodput for s in samples]
    rtts = [s.rtt_ms() for s in samples if s.rtt_ms() is not None]
    elapsed = sum(s.interval for s in samples)
    windows = [s.info["snd_cwnd"] for s in samples if s.info["snd_cwnd"] is not None]
    base_rtts = [s.info["min_rtt"] / 1000 for s in samples if s.info["min_rtt"]]
    base_rtt = min(base_rtts or rtts) if (base_rtts or rtts) else None
    window_bytes = [
        s.info["snd_cwnd"] * s.info["snd_mss"]
        for s in samples
        if s.info["snd_cwnd"] is not None and s.info["snd_mss"] is not None
    ]
    weighted_rate = sum(s.bytes_acked_delta for s in samples) / elapsed
    return {
        "destination": meta.destination(),
        "algorithm": meta.algorithm,
        "repetition": test["repetition"],
        "run_id": meta.run_id,
        "goodput_min_mbps": min(goodput),
        "goodput_median_mbps": median(goodput),
        "goodput_mean_mbps": fmean(goodput),
        "goodput_p95_mbps": percentile(goodput, 0.95),
        "goodput_weighted_mbps": sum(s.bytes_acked_delta for s in samples) * 8 / elapsed / 1e6,
        "rtt_mean_ms": fmean(rtts) if rtts else None,
        "rtt_p95_ms": percentile(rtts, 0.95) if rtts else None,
        "base_rtt_ms": base_rtt,
        "cwnd_median_segments": median(windows) if windows else None,
        "window_median_bytes": median(window_bytes) if window_bytes else None,
        "observed_bdp_bytes": weighted_rate * base_rtt / 1000 if base_rtt is not None else None,
        "retransmitted_segments": sum(s.retrans_delta or 0 for s in samples),
    }


def write_csv(path, rows):
    if not rows:
        path.unlink(missing_ok=True)
        return
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def text_pages(pdf, title, paragraphs):
    lines = []
    for paragraph in paragraphs:
        if paragraph.startswith("#"):
            paragraph = paragraph.lstrip("#").strip()
        lines.extend(wrap(paragraph, 98) if paragraph else [""])
        lines.append("")
    for start in range(0, max(1, len(lines)), 34):
        fig = plt.figure(figsize=(11.7, 8.3))
        fig.text(0.06, 0.94, title, fontsize=16, weight="bold", va="top")
        fig.text(
            0.06,
            0.87,
            "\n".join(lines[start : start + 34]),
            fontsize=10,
            va="top",
            linespacing=1.35,
        )
        pdf.savefig(fig)
        plt.close(fig)


def matched_destinations(manifest, runs):
    expected = {
        (algorithm, repetition)
        for algorithm in manifest["algorithms"]
        for repetition in range(1, manifest["repetitions"] + 1)
    }
    matched = []
    for destination in manifest["selected_destinations"]:
        group = [
            (test, meta, samples)
            for test, (meta, samples) in runs
            if meta.destination() == destination
        ]
        keys = [(meta.algorithm, test["repetition"]) for test, meta, _ in group]
        if len(keys) != len(expected) or set(keys) != expected:
            continue
        if all(
            samples
            and test.get("status", "ok") == "ok"
            and meta.algorithm == test.get("requested_algorithm", meta.algorithm)
            and meta.algorithm == test.get("actual_algorithm", meta.algorithm)
            and meta.destination() == test.get("destination", meta.destination())
            and meta.duration == manifest["config"]["duration"]
            and meta.goodput_interval == manifest["config"]["goodput_interval"]
            for test, meta, samples in group
        ):
            matched.append(destination)
    return matched


def plot_comparison(runs, algorithms, destination, pdf, times_pdf, scatter_pdf):
    selected = [(test, run) for test, run in runs if run[0].destination() == destination]
    colors = {name: plt.get_cmap("tab10")(i % 10) for i, name in enumerate(algorithms)}
    metrics = [
        ("Congestion window (segments)", lambda s: s.info["snd_cwnd"]),
        ("RTT (ms)", lambda s: s.rtt_ms()),
        ("Retransmitted segments / interval", lambda s: s.retrans_delta),
        ("Goodput (Mbit/s)", lambda s: s.goodput),
    ]
    fig, axes = plt.subplots(
        4,
        len(algorithms),
        squeeze=False,
        figsize=(5 * len(algorithms), 12),
        sharey="row",
        sharex=True,
        layout="constrained",
    )
    fig.suptitle(f"{destination} | matched settings; individual repetitions")
    for col, algorithm in enumerate(algorithms):
        axes[0, col].set_title(algorithm)
        for test, (meta, samples) in selected:
            if meta.algorithm != algorithm:
                continue
            for row, (label, pick) in enumerate(metrics):
                axes[row, col].plot(
                    [s.time for s in samples],
                    values(samples, pick),
                    color=colors[algorithm],
                    alpha=0.65,
                    linestyle=["-", "--", ":", "-."][(test["repetition"] - 1) % 4],
                    label=f"Run {test['repetition']}",
                )
                style_axes(axes[row, col])
        axes[0, col].legend(fontsize=8)
        axes[-1, col].set_xlabel("Time (s)")
    for ax in axes.flat:
        ax.set_xlim(left=0)
        ax.set_ylim(bottom=0)
    for row, (label, _) in enumerate(metrics):
        axes[row, 0].set_ylabel(label)
    fig.savefig(times_pdf, bbox_inches="tight", pad_inches=0.15)
    pdf.savefig(fig, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    fig, axes = plt.subplots(
        3,
        len(algorithms),
        squeeze=False,
        figsize=(5 * len(algorithms), 10),
        sharex="row",
        sharey=True,
        layout="constrained",
    )
    fig.suptitle(f"{destination} | all repetitions; common scales per metric")
    for col, algorithm in enumerate(algorithms):
        axes[0, col].set_title(algorithm)
        for test, (meta, samples) in selected:
            if meta.algorithm != algorithm:
                continue
            for row, (label, pick) in enumerate(metrics[:3]):
                axes[row, col].scatter(
                    values(samples, pick),
                    [s.goodput for s in samples],
                    s=10,
                    alpha=0.4,
                    color=colors[algorithm],
                    marker=["o", "x", "^", "s"][(test["repetition"] - 1) % 4],
                    label=f"Run {test['repetition']}",
                )
                axes[row, col].set_xlabel(label)
                style_axes(axes[row, col])
        axes[0, col].legend(fontsize=8)
    for ax in axes.flat:
        ax.set_xlim(left=0)
        ax.set_ylim(bottom=0)
    for ax in axes[:, 0]:
        ax.set_ylabel("Goodput (Mbit/s)")
    fig.savefig(scatter_pdf, bbox_inches="tight", pad_inches=0.15)
    pdf.savefig(fig, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def build_report(manifest, runs, out: Path):
    reports_dir = out / "reports"
    plots_dir = out / "plots"
    reports_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

    matched = matched_destinations(manifest, runs)
    rows = [
        dict(run_statistics(test, run), matched_destination=run[0].destination() in matched)
        for test, run in runs
    ]
    write_csv(reports_dir / "per-test-statistics.csv", rows)
    groups = defaultdict(list)
    for row in rows:
        if row["matched_destination"]:
            groups[row["destination"], row["algorithm"]].append(row)
    aggregates = []
    for (destination, algorithm), group in groups.items():
        means = [r["goodput_weighted_mbps"] for r in group]
        rtts = [r["rtt_mean_ms"] for r in group if r["rtt_mean_ms"] is not None]
        aggregates.append(
            {
                "destination": destination,
                "algorithm": algorithm,
                "runs": len(group),
                "goodput_run_mean_mbps": fmean(means),
                "goodput_run_stddev_mbps": stdev(means) if len(means) > 1 else 0,
                "goodput_run_min_mbps": min(means),
                "goodput_run_max_mbps": max(means),
                "rtt_run_mean_ms": fmean(rtts) if rtts else None,
                "rtt_run_stddev_ms": stdev(rtts) if len(rtts) > 1 else 0,
            }
        )
    write_csv(reports_dir / "destination-algorithm-statistics.csv", aggregates)
    cfg = manifest["config"]
    paragraphs = [
        f"Completed matched destinations: {len(matched)}/{manifest['requested_destinations']}. "
        f"Requested algorithms: {', '.join(manifest['algorithms'])}. "
        f"Repetitions per algorithm: {manifest['repetitions']}. "
        f"Duration: {cfg['duration']} s. Sampling: {cfg['goodput_interval']} s. "
        f"Seed: {manifest['seed']}. Host kernel: {manifest['environment']['kernel']}.",
        f"Test order: {manifest['order_method']}. Each test and its status are recorded in manifest.json. "
        "Destinations were shuffled once, then retained only when every algorithm and repetition succeeded. "
        "The first complete destination is the representative, chosen without comparing throughput. "
        "Failed candidates remain in the manifest and successful partial measurements remain on disk.",
        "The per-run summary gives minimum, median, arithmetic mean, and P95 sampled goodput, "
        "duration-weighted goodput, mean/P95 RTT, and retransmitted segments. P95 uses linear "
        "interpolation at index (n - 1) * 0.95 in the sorted samples. Aggregate throughput is the mean "
        "of duration-weighted per-run goodputs; variability is sample standard deviation across runs. "
        "RTT aggregates average the sampled smoothed RTT, not independent packet RTT observations.",
    ]
    if not matched:
        paragraphs.append(
            "No complete matched destination is available. There is no measured "
            "algorithm comparison to interpret yet."
        )
    excluded = set(manifest["selected_destinations"]) - set(matched)
    if excluded:
        paragraphs.append(
            "Excluded incomplete or mismatched destination groups: "
            + ", ".join(sorted(excluded))
            + ". Check manifest.json and run metadata."
        )
    for destination in matched:
        group = [r for r in aggregates if r["destination"] == destination]
        fastest = max(group, key=lambda r: r["goodput_run_mean_mbps"])
        valid_rtt = [r for r in group if r["rtt_run_mean_ms"] is not None]
        lowest = min(valid_rtt, key=lambda r: r["rtt_run_mean_ms"]) if valid_rtt else None
        paragraphs.append(
            f"{destination}: highest measured mean goodput: {fastest['algorithm']} "
            f"({fastest['goodput_run_mean_mbps']:.3f} Mbit/s). "
            + (
                f"Lowest measured mean RTT: {lowest['algorithm']} "
                f"({lowest['rtt_run_mean_ms']:.3f} ms)."
                if lowest
                else "RTT unavailable."
            )
        )
        for row in group:
            paragraphs.append(
                f"  {row['algorithm']}: mean goodput "
                f"{row['goodput_run_mean_mbps']:.3f} Mbit/s, run standard deviation "
                f"{row['goodput_run_stddev_mbps']:.3f}, range "
                f"{row['goodput_run_min_mbps']:.3f}-{row['goodput_run_max_mbps']:.3f}."
            )
    if rows:
        paragraphs.append("Per-run statistics (goodput in Mbit/s; RTT in ms):")
        for row in rows:
            rtt_text = (
                f"{row['rtt_mean_ms']:.3f}" if row["rtt_mean_ms"] is not None else "unavailable"
            )
            paragraphs.append(
                f"{row['destination']} {row['algorithm']} run {row['repetition']}: "
                f"goodput min/median/mean/P95 = {row['goodput_min_mbps']:.3f} / "
                f"{row['goodput_median_mbps']:.3f} / {row['goodput_mean_mbps']:.3f} / "
                f"{row['goodput_p95_mbps']:.3f}; mean RTT = {rtt_text}; "
                f"retransmitted segments = {row['retransmitted_segments']}; "
                f"matched destination = {row['matched_destination']}."
            )
            if row["base_rtt_ms"] is not None and row["window_median_bytes"] is not None:
                paragraphs.append(
                    f"Window/RTT context: minimum filtered RTT {row['base_rtt_ms']:.3f} ms; "
                    f"median cwnd {row['cwnd_median_segments']:.1f} segments "
                    f"({row['window_median_bytes']:.0f} bytes); observed-rate BDP proxy "
                    f"{row['observed_bdp_bytes']:.0f} bytes. This proxy uses achieved goodput, "
                    "so it cannot independently identify bottleneck capacity."
                )
    paragraphs += [
        "Interpretation: cwnd limits in-flight segments; its byte budget is cwnd * MSS. "
        "Without another bottleneck, the window-limited rate is approximately cwnd * MSS / RTT. "
        "The bandwidth-delay product estimates bytes needed in flight at bottleneck bandwidth and "
        "base RTT. Extra in-flight bytes can accumulate in queues. RTT growth at similar goodput is "
        "consistent with extra queueing; a larger cwnd alone does not establish higher useful throughput.",
        "Reno increases its congestion window additively during congestion avoidance and reduces it "
        "after loss. CUBIC probes with a cubic window trajectory and can recover capacity faster on "
        "large bandwidth-delay paths. BBR estimates delivery bandwidth and propagation RTT and uses "
        "a model with pacing. These are expected mechanisms, not evidence that a particular algorithm "
        "won on an unmeasured network regime. The installed BBR version depends on the host kernel.",
        "Retransmissions are a loss proxy, not a direct packet-loss probability. Reordering and "
        "spurious retransmissions can contribute. Window reductions may precede a later goodput drop; "
        "simultaneous scatter plots do not capture every delayed response. Public-server rate caps, "
        "receiver windows, CPU limits, and application limits can hide congestion-control differences.",
        "Limitations: sequential tests share destinations and settings but cannot hold Internet "
        "cross-traffic or routes constant. Rotating order reduces systematic order bias without "
        "eliminating it. Short runs include startup. Excluding failed candidate groups can bias the "
        "sample toward reliable servers. Differences of the same magnitude as run variability are "
        "not strong evidence of an advantage. Establishing operating regimes causally requires "
        "controlled bottleneck bandwidth, RTT, queue size, and loss; public traces alone are insufficient.",
        "AI assistance: an AI coding assistant helped implement experiment automation, plotting, "
        "and draft the algorithm design and explanatory text.",
    ]
    (reports_dir / "algorithm-comparison-report.md").write_text(
        "# TCP congestion control comparison\n\n" + "\n\n".join(paragraphs) + "\n"
    )
    with PdfPages(reports_dir / "algorithm-comparison-report.pdf") as pdf:
        text_pages(pdf, "TCP congestion control comparison", paragraphs)
        for start in range(0, len(rows), 18):
            page_rows = rows[start : start + 18]
            fig, ax = plt.subplots(figsize=(15, 8), layout="constrained")
            ax.axis("off")
            ax.set_title("Per-run goodput summary (Mbit/s); * = incomplete destination group")
            table = ax.table(
                cellText=[
                    [
                        r["destination"] + ("" if r["matched_destination"] else "*"),
                        r["algorithm"],
                        r["repetition"],
                        *[
                            f"{r[key]:.3f}"
                            for key in (
                                "goodput_min_mbps",
                                "goodput_median_mbps",
                                "goodput_mean_mbps",
                                "goodput_p95_mbps",
                            )
                        ],
                    ]
                    for r in page_rows
                ],
                colLabels=["Destination", "Algorithm", "Run", "Min", "Median", "Mean", "P95"],
                cellLoc="center",
                loc="center",
                colWidths=[0.3, 0.13, 0.07, 0.12, 0.12, 0.12, 0.12],
            )
            table.auto_set_font_size(False)
            table.set_fontsize(9)
            table.scale(1, 1.6)
            pdf.savefig(fig)
            plt.close(fig)
        for destination in matched:
            destination_runs = [
                (test, run) for test, run in runs if run[0].destination() == destination
            ]
            fig, ax = plt.subplots(figsize=(11.7, 5), layout="constrained")
            colors = {
                name: plt.get_cmap("tab10")(i % 10) for i, name in enumerate(manifest["algorithms"])
            }
            for test, (meta, samples) in destination_runs:
                ax.plot(
                    [s.time for s in samples],
                    [s.goodput for s in samples],
                    alpha=0.65,
                    color=colors[meta.algorithm],
                    linestyle=["-", "--", ":", "-."][(test["repetition"] - 1) % 4],
                    label=f"{meta.algorithm} r{test['repetition']}",
                )
            ax.set(title=destination, xlabel="Time (s)", ylabel="Goodput (Mbit/s)", ylim=(0, None))
            ax.legend(fontsize=8, ncol=min(len(manifest["algorithms"]), 4))
            style_axes(ax)
            pdf.savefig(fig)
            plt.close(fig)
        representative = manifest["representative"]
        if representative not in matched:
            representative = matched[0] if matched else None
        if representative in matched:
            plot_comparison(
                runs,
                manifest["algorithms"],
                representative,
                pdf,
                plots_dir / "algorithm-metrics-over-time.pdf",
                plots_dir / "algorithm-metrics-vs-goodput.pdf",
            )
        else:
            (plots_dir / "algorithm-metrics-over-time.pdf").unlink(missing_ok=True)
            (plots_dir / "algorithm-metrics-vs-goodput.pdf").unlink(missing_ok=True)
        design = Path(__file__).with_name("Q3_DESIGN.md")
        if design.exists():
            text_pages(
                pdf, "Controller design reference (Q3_DESIGN.md)", design.read_text().splitlines()
            )
    for test, (meta, samples) in runs:
        save_run_plots(meta, samples, out / "tcp-traces" / meta.slug())
