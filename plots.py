# All PDF plotting. Functions take RunMetadata/Sample rather than Server/TestResult so
# that this module stays independent of destinations.py and client.py.

from collections.abc import Callable
from pathlib import Path
from statistics import fmean, median, quantiles
from textwrap import fill

import matplotlib
from matplotlib.transforms import Bbox

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle

from log_utils import log_message
from measurement import RunMetadata, Sample

GOODPUT_GRAPHS_NAME = "destination-goodput-over-time.pdf"
SUMMARY_TABLE_NAME = "destination-goodput-statistics.pdf"

CWND_COLOR = "#2f6f9f"
RTT_COLOR = "#0f766e"
LOSS_COLOR = "#b02a37"
GOODPUT_COLOR = "#5b4b8a"
TEXT_COLOR = "#20344b"
MUTED_COLOR = "#596779"

type Run = tuple[RunMetadata, list[Sample]]


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


def cumulative(samples: list[Sample]) -> list[float]:
    total = 0.0
    totals: list[float] = []

    for sample in samples:
        total += sample.retrans_delta or 0
        totals.append(total)

    return totals


def plot_time_series(meta: RunMetadata, samples: list[Sample], path: Path) -> None:
    # Q2(b)(i): snd_cwnd, RTT, loss proxy and goodput against time.
    if not samples:
        log_message("destinations", "No samples; skipping time series plot")
        return

    times = values(samples, lambda s: s.time)

    fig, axes = plt.subplots(4, 1, figsize=(11, 12), sharex=True, layout="constrained")
    fig.suptitle(run_title(meta), fontsize=12, color=TEXT_COLOR)

    cwnd_ax, rtt_ax, loss_ax, goodput_ax = axes

    cwnd = values(samples, lambda s: s.info["snd_cwnd"])
    ssthresh = values(samples, lambda s: s.info["snd_ssthresh"])
    cwnd_ax.plot(times, cwnd, color=CWND_COLOR, linewidth=1.5, label="snd_cwnd")

    # ssthresh is 2**32-1 while the sender is in slow start; that would flatten the axis.
    finite_ssthresh = [v if v < 2**31 else float("nan") for v in ssthresh]
    cwnd_ax.plot(
        times,
        finite_ssthresh,
        color=MUTED_COLOR,
        linewidth=1.1,
        linestyle="--",
        label="snd_ssthresh",
    )
    cwnd_ax.set_ylabel("Congestion window\n(segments)", fontsize=11)
    cwnd_ax.legend(fontsize=9, frameon=False, loc="upper right")

    srtt = values(samples, lambda s: s.rtt_ms())
    rttvar = values(samples, lambda s: s.rttvar_ms())
    min_rtt = values(samples, lambda s: None if s.info["min_rtt"] is None else s.info["min_rtt"] / 1000)

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
    rtt_ax.plot(times, min_rtt, color=MUTED_COLOR, linewidth=1.1, linestyle="--", label="min_rtt")
    rtt_ax.set_ylabel("RTT (ms)", fontsize=11)
    rtt_ax.set_ylim(bottom=0)
    rtt_ax.legend(fontsize=9, frameon=False, loc="upper right")

    retrans = values(samples, lambda s: s.retrans_delta)
    width = median([s.interval for s in samples]) * 0.85
    loss_ax.bar(times, retrans, width=width, color=LOSS_COLOR, alpha=0.75, label="retransmits")
    loss_ax.set_ylabel("Retransmitted\nsegments per interval", fontsize=11)
    loss_ax.set_ylim(bottom=0)

    total_ax = loss_ax.twinx()
    total_ax.plot(
        times, cumulative(samples), color=TEXT_COLOR, linewidth=1.3, label="cumulative"
    )
    total_ax.set_ylabel("Cumulative", fontsize=11)
    total_ax.set_ylim(bottom=0)
    total_ax.spines["top"].set_visible(False)

    handles = loss_ax.get_legend_handles_labels()[0] + total_ax.get_legend_handles_labels()[0]
    labels = loss_ax.get_legend_handles_labels()[1] + total_ax.get_legend_handles_labels()[1]
    loss_ax.legend(handles, labels, fontsize=9, frameon=False, loc="upper right")

    goodput = values(samples, lambda s: s.goodput)
    goodput_ax.plot(times, goodput, color=GOODPUT_COLOR, linewidth=1.5)
    goodput_ax.set_ylabel("Goodput (Mbit/s)", fontsize=11)
    goodput_ax.set_xlabel("Time (s)", fontsize=12)
    goodput_ax.set_ylim(bottom=0)
    goodput_ax.set_xlim(left=0)

    for ax in axes:
        style_axes(ax)
        ax.tick_params(labelbottom=True)

    fig.align_ylabels(axes)
    fig.savefig(path, format="pdf", bbox_inches="tight")
    plt.close(fig)

    log_message("test", f"Time series saved to {path}")


def plot_scatter(meta: RunMetadata, samples: list[Sample], path: Path) -> None:
    # Q2(b)(ii): each TCP metric against the goodput measured over the same interval.
    if not samples:
        log_message("destinations", "No samples; skipping scatter plot")
        return

    goodput = values(samples, lambda s: s.goodput)

    panels = (
        ("snd_cwnd (segments)", values(samples, lambda s: s.info["snd_cwnd"]), CWND_COLOR),
        ("srtt (ms)", values(samples, lambda s: s.rtt_ms()), RTT_COLOR),
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
        ax.set_ylim(bottom=0)
        style_axes(ax)

    fig.savefig(path, format="pdf", bbox_inches="tight")
    plt.close(fig)

    log_message("test", f"Scatter plots saved to {path}")


def save_run_plots(meta: RunMetadata, samples: list[Sample], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    plot_time_series(meta, samples, out_dir / "tcp-metrics-over-time.pdf")
    plot_scatter(meta, samples, out_dir / "tcp-metrics-vs-goodput.pdf")


def plot_destinations(runs: list[Run], path: Path) -> None:
    num_dest = len(runs)

    if num_dest == 0:
        log_message("destinations", "No successful tests; skipping plot")
        return

    num_cols = min(2, num_dest)
    num_rows = (num_dest + num_cols - 1) // num_cols

    fig, axes = plt.subplots(
        num_rows,
        num_cols,
        figsize=(11, 4 * num_rows + 1),
        sharex=True,
        sharey=True,
        squeeze=False,
        layout="constrained",
    )
    fig.get_layout_engine().set(w_pad=0.16, h_pad=0.16)
    fig.suptitle("Throughput Per Destination", fontsize=14)

    max_goodput = 0

    for ax, (meta, samples) in zip(axes.flat[:num_dest], runs, strict=True):
        goodput = [sample.goodput for sample in samples]
        max_goodput = max(max_goodput, max(goodput))

        times = [sample.time for sample in samples]
        ax.plot(times, goodput, linewidth=1.5)

        ax.set_title(f"{meta.destination()}\n{meta.algorithm}", fontsize=11)
        ax.set_xlabel("Time (s)", fontsize=12)
        ax.set_ylabel("Throughput (Mbit/s)", fontsize=12)

        ax.tick_params(axis="both", labelsize=10, labelbottom=True, labelleft=True)

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        ax.grid(axis="y", linestyle="--", alpha=0.25, linewidth=0.7)
        ax.set_axisbelow(True)

    axes[0, 0].set_xlim(left=0)
    axes[0, 0].set_ylim(bottom=0, top=max(max_goodput * 1.1, 1))

    for ax in axes.flat[num_dest:]:
        ax.set_visible(False)

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    fig.set_layout_engine("none")

    for ax in axes.flat[:num_dest]:
        bounds = ax.get_tightbbox(renderer).padded(6 * fig.dpi / 72)
        bounds = bounds.transformed(fig.transFigure.inverted())

        fig.add_artist(
            Rectangle(
                (bounds.x0, bounds.y0),
                bounds.width,
                bounds.height,
                transform=fig.transFigure,
                fill=False,
                edgecolor="#a8b3bf",
                linewidth=0.8,
            )
        )

    fig.savefig(path, format="pdf", bbox_inches="tight")
    plt.close(fig)

    log_message("destinations", f"Plot saved to {path}")


def save_summary_table(runs: list[Run], path: Path) -> None:
    percentile = 95
    rows: list[list[str]] = []

    for meta, samples in runs:
        goodput = [sample.goodput for sample in samples]
        quant = quantiles(goodput, n=100, method="inclusive")
        stats = (min(goodput), median(goodput), fmean(goodput), quant[percentile - 1])
        stats_fmt = [f"{value:,.2f}" for value in stats]
        rows.append([fill(meta.destination(), width=48), meta.algorithm, *stats_fmt])

    rows_per_page = 15
    top_space = 1.1
    bottom_space = 0.5
    text_spacing = 0.4
    left_margin = 0.04
    right_edge = 1 - left_margin
    column_widths = (0.40, 0.10, 0.10, 0.11, 0.10, 0.10)
    table_width = sum(column_widths)

    num_pages = max(1, (len(rows) + rows_per_page - 1) // rows_per_page)

    with PdfPages(path) as pdf:
        for page in range(num_pages):
            page_rows = rows[page * rows_per_page : (page + 1) * rows_per_page]

            table_height = 0.34 * (len(page_rows) + 1) if page_rows else 0.5
            page_height = table_height + top_space + bottom_space

            fig, ax = plt.subplots(figsize=(11.7, page_height))

            fig.subplots_adjust(
                left=left_margin,
                right=right_edge,
                bottom=bottom_space / page_height,
                top=1 - top_space / page_height,
            )
            fig.text(
                left_margin,
                1 - text_spacing / page_height,
                "Goodput Summary",
                fontsize=20,
                weight="bold",
                color=TEXT_COLOR,
            )
            fig.text(
                left_margin,
                1 - 2 * text_spacing / page_height,
                f"{len(rows)} destinations | Throughput in Mbit/s",
                fontsize=11,
                color=MUTED_COLOR,
            )

            ax.set_axis_off()

            if page_rows:
                table = ax.table(
                    cellText=page_rows,
                    colLabels=[
                        "Destination",
                        "Algorithm",
                        "Min",
                        "Median",
                        "Mean",
                        rf"$P_{{{percentile}}}$",
                    ],
                    colWidths=column_widths,
                    cellLoc="center",
                    colLoc="center",
                    bbox=Bbox.from_bounds((1 - table_width) / 2, 0, table_width, 1),
                )

                table.auto_set_font_size(False)
                table.set_fontsize(9)

                for (row, _), cell in table.get_celld().items():
                    cell.set_linewidth(0)
                    cell.PAD = 0.06

                    text = cell.get_text()

                    if row == 0:
                        cell.set_facecolor(TEXT_COLOR)
                        text.set_color("white")
                        text.set_fontweight("bold")
                    else:
                        cell.set_facecolor("#edf2f7" if row % 2 else "white")
                        text.set_color(TEXT_COLOR)
            else:
                ax.text(0, 0.5, "No successful tests to summarize.", fontsize=12, color=MUTED_COLOR)

            fig.text(
                right_edge,
                0.18 / page_height,
                f"{page + 1} / {num_pages}",
                ha="right",
                fontsize=9,
                color=MUTED_COLOR,
            )

            pdf.savefig(fig)
            plt.close(fig)

    log_message("destinations", f"Summary saved to {path}")
