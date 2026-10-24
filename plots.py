# All PDF plotting. Functions take RunMetadata/Sample rather than Server/TestResult so
# that this module stays independent of destinations.py and client.py.

from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from statistics import fmean, median

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from log_utils import log_message
from measurement import Run, RunMetadata, Sample, percentile

GOODPUT_GRAPHS_NAME = "destination-goodput-over-time.pdf"
SUMMARY_TABLE_NAME = "destination-goodput-statistics.pdf"

CWND_COLOR = "#2f6f9f"
RTT_COLOR = "#0f766e"
LOSS_COLOR = "#b02a37"
GOODPUT_COLOR = "#5b4b8a"
TEXT_COLOR = "#20344b"
MUTED_COLOR = "#596779"

# Fixed per algorithm so a color means the same algorithm in every figure.
ALGORITHM_COLORS = {"cubic": "#2a78d6", "reno": "#eb6834", "bbr": "#1baf7a"}
LINE_STYLES = ["-", "--", ":", "-."]

# Linux reports an unlimited slow-start threshold as 2**31 - 1.
INFINITE_SSTHRESH = 2**31 - 1


def algorithm_color(name: str) -> str:
    return ALGORITHM_COLORS.get(name, MUTED_COLOR)


def values(samples: list[Sample], pick: Callable[[Sample], float | int | None]) -> list[float]:
    # Missing fields (older kernel, or no delta available) become NaN so matplotlib
    # leaves a gap instead of drawing a misleading zero.
    return [float("nan") if (value := pick(sample)) is None else float(value) for sample in samples]


def style_axes(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linestyle="--", alpha=0.25, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", labelsize=10)


def run_title(meta: RunMetadata) -> str:
    return (
        f"{meta.destination()}  |  {meta.algorithm}  |  run {meta.run_id}\n"
        f"{meta.duration}s transfer, {meta.goodput_interval}s sampling interval, "
        f"kernel {meta.kernel}"
    )


def plot_time_series(meta: RunMetadata, samples: list[Sample], path: Path) -> None:
    # Q2(b)(i): snd_cwnd, RTT, loss proxy and goodput against time.
    times = values(samples, lambda s: s.time)

    fig, axes = plt.subplots(4, 1, figsize=(11, 12), sharex=True, layout="constrained")
    fig.suptitle(run_title(meta), fontsize=12, color=TEXT_COLOR)
    cwnd_ax, rtt_ax, loss_ax, goodput_ax = axes

    cwnd_ax.plot(
        times,
        values(samples, lambda s: s.info["snd_cwnd"]),
        color=CWND_COLOR,
        linewidth=1.5,
        label="snd_cwnd",
    )
    # Omit the "unlimited" threshold (before the first loss) so it doesn't squash the axis.
    ssthresh = values(
        samples,
        lambda s: (
            None if s.info["snd_ssthresh"] in (None, INFINITE_SSTHRESH) else s.info["snd_ssthresh"]
        ),
    )
    cwnd_ax.plot(
        times, ssthresh, color=MUTED_COLOR, linewidth=1.1, linestyle="--", label="snd_ssthresh"
    )
    cwnd_ax.set_ylabel("Congestion window\n(segments)", fontsize=11)

    srtt = values(samples, lambda s: s.ms("rtt"))
    rttvar = values(samples, lambda s: s.ms("rttvar"))
    rtt_ax.plot(times, srtt, color=RTT_COLOR, linewidth=1.5, label="srtt")
    rtt_ax.fill_between(
        times,
        [s - v for s, v in zip(srtt, rttvar, strict=True)],
        [s + v for s, v in zip(srtt, rttvar, strict=True)],
        color=RTT_COLOR,
        alpha=0.18,
        linewidth=0,
        label="srtt ± rttvar",
    )
    rtt_ax.plot(
        times,
        values(samples, lambda s: s.ms("min_rtt")),
        color=MUTED_COLOR,
        linewidth=1.1,
        linestyle="--",
        label="min_rtt",
    )
    rtt_ax.set_ylabel("RTT (ms)", fontsize=11)

    # Each bar spans the interval its retransmissions were counted over.
    loss_ax.bar(
        [s.time - s.interval for s in samples],
        values(samples, lambda s: s.retrans_delta),
        width=[s.interval * 0.85 for s in samples],
        align="edge",
        color=LOSS_COLOR,
        alpha=0.75,
    )
    loss_ax.set_ylabel("Retransmitted\nsegments per interval", fontsize=11)

    goodput_ax.plot(times, values(samples, lambda s: s.goodput), color=GOODPUT_COLOR, linewidth=1.5)
    goodput_ax.set_ylabel("Goodput (Mbit/s)", fontsize=11)
    goodput_ax.set_xlabel("Time (s)", fontsize=12)

    for ax in axes:
        style_axes(ax)
        ax.set_ylim(bottom=0)
        ax.tick_params(labelbottom=True)
    cwnd_ax.legend(fontsize=9, frameon=False, loc="upper right")
    rtt_ax.legend(fontsize=9, frameon=False, loc="lower right")
    goodput_ax.set_xlim(left=0)

    fig.align_ylabels(axes)
    fig.savefig(path, format="pdf", bbox_inches="tight")
    plt.close(fig)
    log_message("test", f"Time series saved to {path}")


def plot_scatter(meta: RunMetadata, samples: list[Sample], path: Path) -> None:
    # Q2(b)(ii): each TCP metric against the goodput measured over the same interval.
    goodput = values(samples, lambda s: s.goodput)
    panels = (
        ("snd_cwnd (segments)", values(samples, lambda s: s.info["snd_cwnd"]), CWND_COLOR),
        ("srtt (ms)", values(samples, lambda s: s.ms("rtt")), RTT_COLOR),
        (
            "Retransmitted segments per interval",
            values(samples, lambda s: s.retrans_delta),
            LOSS_COLOR,
        ),
    )

    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True, layout="constrained")
    fig.suptitle(run_title(meta), fontsize=12, color=TEXT_COLOR)

    for ax, (label, x, color) in zip(axes, panels, strict=True):
        ax.scatter(x, goodput, s=26, color=color, alpha=0.6, edgecolors="white", linewidths=0.5)
        ax.set_xlabel(label, fontsize=11)
        ax.set_ylabel("Goodput (Mbit/s)", fontsize=11)
        ax.tick_params(labelleft=True)
        ax.set_xlim(left=0)
        ax.set_ylim(bottom=0)
        style_axes(ax)

    fig.savefig(path, format="pdf", bbox_inches="tight")
    plt.close(fig)
    log_message("test", f"Scatter plots saved to {path}")


def save_run_plots(meta: RunMetadata, samples: list[Sample], out_dir: Path) -> None:
    if not samples:
        log_message("error", f"{meta.destination()} has no samples; skipping TCP plots")
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    plot_time_series(meta, samples, out_dir / "tcp-metrics-over-time.pdf")
    plot_scatter(meta, samples, out_dir / "tcp-metrics-vs-goodput.pdf")


def run_order(run: Run) -> tuple[int, str]:
    # Known algorithms in a fixed order (cubic, reno, bbr), then by run ID (repetition).
    algorithms = list(ALGORITHM_COLORS)
    meta = run[0]
    position = algorithms.index(meta.algorithm) if meta.algorithm in algorithms else len(algorithms)
    return position, meta.run_id


def by_destination(runs: list[Run]) -> dict[str, list[Run]]:
    """Runs grouped by destination (in first-seen order), each group in run_order."""
    groups: dict[str, list[Run]] = defaultdict(list)
    for run in runs:
        groups[run[0].destination()].append(run)
    return {destination: sorted(group, key=run_order) for destination, group in groups.items()}


def plot_destinations(runs: list[Run], path: Path, pdf: PdfPages | None = None) -> None:
    # Q1(c): goodput over time, one panel per destination, one line per run.
    groups = by_destination([run for run in runs if run[1]])
    if not groups:
        log_message("destinations", "No successful tests; skipping goodput plot")
        return

    cols = min(2, len(groups))
    rows = -(-len(groups) // cols)
    fig, axes = plt.subplots(
        rows,
        cols,
        figsize=(11, 3.6 * rows + 0.8),
        sharex=True,
        sharey=True,
        squeeze=False,
        layout="constrained",
    )
    fig.suptitle("Goodput over time per destination", fontsize=14, color=TEXT_COLOR)

    for ax, (destination, group) in zip(axes.flat, groups.items(), strict=False):
        repetition: dict[str, int] = defaultdict(int)
        for meta, samples in group:
            repetition[meta.algorithm] += 1
            ax.plot(
                [s.time for s in samples],
                [s.goodput for s in samples],
                linewidth=1.2,
                color=algorithm_color(meta.algorithm),
                alpha=0.8,
                linestyle=LINE_STYLES[(repetition[meta.algorithm] - 1) % len(LINE_STYLES)],
                label=f"{meta.algorithm} run {repetition[meta.algorithm]}",
            )
        ax.set_title(destination, fontsize=11, color=TEXT_COLOR)
        ax.set_xlabel("Time (s)", fontsize=11)
        ax.set_ylabel("Goodput (Mbit/s)", fontsize=11)
        ax.tick_params(labelbottom=True, labelleft=True)
        style_axes(ax)

    axes[0, 0].set_xlim(left=0)
    axes[0, 0].set_ylim(bottom=0)
    for ax in axes.flat[len(groups) :]:
        ax.set_visible(False)

    # Colors and line styles mean the same thing in every panel, so one legend serves all.
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="outside lower center",
        ncols=min(len(labels), 3),
        fontsize=9,
        frameon=False,
    )

    fig.savefig(path, format="pdf", bbox_inches="tight")
    if pdf is not None:
        pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    log_message("destinations", f"Goodput plot saved to {path}")


def save_summary_table(runs: list[Run], path: Path) -> None:
    # Q1(c): min / median / mean / P95 goodput for each destination and algorithm,
    # pooling the samples of repeated runs.
    pooled: dict[tuple[str, str], list[float]] = defaultdict(list)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for group in by_destination(runs).values():
        for meta, samples in group:
            if samples:
                key = (meta.destination(), meta.algorithm)
                pooled[key] += [s.goodput for s in samples]
                counts[key] += 1

    rows = [
        [
            destination,
            algorithm,
            str(counts[destination, algorithm]),
            *(f"{v:,.2f}" for v in (min(g), median(g), fmean(g), percentile(g, 0.95))),
        ]
        for (destination, algorithm), g in pooled.items()
    ]

    fig, ax = plt.subplots(figsize=(11.7, 0.9 + 0.3 * (len(rows) + 1)), layout="constrained")
    ax.set_axis_off()
    fig.suptitle(
        "Goodput summary (Mbit/s; repeated runs pooled)",
        fontsize=14,
        weight="bold",
        color=TEXT_COLOR,
    )

    if rows:
        table = ax.table(
            cellText=rows,
            colLabels=["Destination", "Algorithm", "Runs", "Min", "Median", "Mean", "P95"],
            colWidths=[0.40, 0.11, 0.07, 0.10, 0.10, 0.10, 0.10],
            cellLoc="center",
            bbox=[0, 0, 1, 1],
        )
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        for (row, _), cell in table.get_celld().items():
            cell.set_linewidth(0)
            cell.set_facecolor(TEXT_COLOR if row == 0 else ("#edf2f7" if row % 2 else "white"))
            cell.get_text().set_color("white" if row == 0 else TEXT_COLOR)
            if row == 0:
                cell.get_text().set_fontweight("bold")
    else:
        ax.text(0, 0.5, "No successful tests to summarize.", fontsize=12, color=MUTED_COLOR)

    fig.savefig(path, format="pdf", bbox_inches="tight")
    plt.close(fig)
    log_message("destinations", f"Summary saved to {path}")


def save_destination_outputs(runs: list[Run], out: Path) -> None:
    """Q1 goodput plot and summary table, plus per-trace TCP plots for every run."""
    (out / "plots").mkdir(parents=True, exist_ok=True)
    (out / "reports").mkdir(parents=True, exist_ok=True)
    save_summary_table(runs, out / "reports" / SUMMARY_TABLE_NAME)
    plot_destinations(runs, out / "plots" / GOODPUT_GRAPHS_NAME)
    for meta, samples in runs:
        save_run_plots(meta, samples, out / "tcp-traces" / meta.slug())
