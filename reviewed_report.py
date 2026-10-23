from pathlib import Path
from statistics import fmean, stdev
from textwrap import wrap

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from comparison_plots import matched_destinations, plot_comparison, run_statistics


def sections(document):
    result = {}
    name = None
    for line in document.splitlines():
        if line.startswith("## "):
            name = line[3:]
            result[name] = []
        elif name is not None:
            result[name].append(line)
    return {name: "\n".join(lines).strip() for name, lines in result.items()}


def page(title, number):
    fig = plt.figure(figsize=(8.5, 11))
    fig.text(0.075, 0.95, title, family="serif", fontsize=15, weight="bold", va="top")
    fig.text(0.925, 0.025, str(number), fontsize=9, ha="right")
    return fig


def prose(fig, text, y, *, size=10.5, spacing=0.018, bottom=0.04):
    for paragraph in text.split("\n\n"):
        code = paragraph.startswith(("State:", "```"))
        source_lines = paragraph.splitlines()
        if paragraph.startswith("```"):
            source_lines = source_lines[1:-1]
        lines = []
        for line in source_lines:
            indent = len(line) - len(line.lstrip())
            lines.extend(wrap(line, width=85, subsequent_indent=" " * indent) or [""])
        for line in lines:
            if y < bottom:
                raise ValueError("Report text exceeds its page; shorten the reviewed text")
            fig.text(
                0.075,
                y,
                line,
                fontsize=9 if code else size,
                va="top",
                family="monospace" if code else "serif",
            )
            y -= spacing
        y -= spacing * 0.5
    return y


class PlotPages:
    def __init__(self, pdf):
        self.pdf = pdf
        self.number = 3

    def savefig(self, fig, **kwargs):
        fig.set_size_inches(8.5, 11)
        fig._suptitle.set_text(
            "3(a): Representative destination — time series"
            if self.number == 3
            else "3(a): Representative destination — scatter plots"
        )
        fig._suptitle.set_fontsize(12)
        for ax in fig.axes:
            ax.xaxis.label.set_fontsize(8)
            ax.yaxis.label.set_fontsize(8)
            ax.title.set_fontsize(10)
            ax.tick_params(labelsize=7)
            legend = ax.get_legend()
            if legend:
                for text in legend.get_texts():
                    text.set_fontsize(6.5)
        fig.canvas.draw()
        self.pdf.savefig(fig, bbox_inches="tight", pad_inches=0.18)
        self.number += 1


def build_reviewed_report(manifest, runs, out: Path, report_path: Path | None = None):
    report_path = report_path or out / "reports" / "reviewed-algorithm-comparison.pdf"
    destinations = matched_destinations(manifest, runs)
    # This template embeds Assignment 2's reviewed prose, not new experiment conclusions.
    if set(manifest["algorithms"]) != {"cubic", "reno", "bbr"} or not destinations:
        report_path.unlink(missing_ok=True)
        return
    if not (out / "observations.md").exists():
        return
    source = Path(__file__).with_name("Q3_REPORT.md")
    text = sections(source.read_text())
    matched = [
        (test, run)
        for test, run in runs
        if run[0].destination() in destinations
    ]
    rows = [run_statistics(test, run) for test, run in matched]
    support = out / "plots" / "reviewed-report-figures"
    support.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(report_path) as pdf:
        fig = page("3(a): Compare CUBIC, Reno, and BBR", 1)
        prose(fig, text["Method"], 0.90, bottom=0.49)
        table_rows = []
        for index, destination in enumerate(destinations, 1):
            for algorithm in manifest["algorithms"]:
                group = [
                    row
                    for row in rows
                    if row["destination"] == destination and row["algorithm"] == algorithm
                ]
                goodput = [row["goodput_weighted_mbps"] for row in group]
                rtts = [row["rtt_mean_ms"] for row in group]
                spread = stdev(goodput) if len(goodput) > 1 else 0
                table_rows.append(
                    [
                        f"D{index}",
                        algorithm,
                        f"{fmean(goodput):.2f} ± {spread:.2f}",
                        f"{fmean(rtts):.2f}",
                        sum(row["retransmitted_segments"] for row in group),
                    ]
                )
        ax = fig.add_axes([0.075, 0.25, 0.85, 0.25])
        ax.axis("off")
        table = ax.table(
            cellText=table_rows,
            colLabels=["Dest.", "Algorithm", "Goodput (Mbit/s)", "RTT (ms)", "Retrans."],
            colWidths=[0.10, 0.17, 0.33, 0.20, 0.20],
            cellLoc="center",
            bbox=[0, 0, 1, 1],
        )
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        for (row, _), cell in table.get_celld().items():
            cell.set_linewidth(0.4)
            if row == 0:
                cell.set_facecolor("#edf0f4")
                cell.get_text().set_weight("bold")
        for index, destination in enumerate(destinations, 1):
            fig.text(
                0.075,
                0.225 - (index - 1) * 0.018,
                f"D{index}: {destination}",
                fontsize=9,
                family="serif",
            )
        fig.text(
            0.075,
            0.15,
            f"Reproduce: python main.py analyze --manifest {out / 'manifest.json'}",
            fontsize=8.5,
        )
        fig.text(
            0.075,
            0.13,
            f"Raw data and full min/median/mean/P95 tables: {out}/",
            fontsize=9,
            family="serif",
        )
        base = "https://github.com/aunali0/CS422_assignment_2"
        for index, (label, path) in enumerate(
            [
                ("Repository", ""),
                ("Data socket selection", "/blob/4389022/client.py#L53"),
                ("Experiment runner", "/blob/4389022/comparison.py#L51"),
                ("Statistics and plots", "/blob/main/comparison_plots.py"),
            ]
        ):
            fig.text(
                0.075 + (index % 2) * 0.43,
                0.095 - (index // 2) * 0.02,
                label,
                color="#245b9b",
                fontsize=9,
                url=base + path,
            )
        pdf.savefig(fig)
        plt.close(fig)

        fig = page("3(a): Observations and limitations", 2)
        prose(fig, text["Observations"], 0.90, bottom=0.12)
        references = [
            (
                "[1] RFC 5681: Reno congestion avoidance",
                "https://www.rfc-editor.org/rfc/rfc5681.html#section-3.1",
            ),
            ("[2] RFC 9438: CUBIC", "https://www.rfc-editor.org/rfc/rfc9438.html"),
            (
                "[3] Google BBR documentation",
                "https://github.com/google/bbr/blob/master/Documentation/bbr-faq.md",
            ),
        ]
        for index, (label, url) in enumerate(references):
            fig.text(0.075, 0.085 - index * 0.018, label, fontsize=8.5, color="#245b9b", url=url)
        pdf.savefig(fig)
        plt.close(fig)

        plot_comparison(
            matched,
            manifest["algorithms"],
            manifest["representative"] if manifest["representative"] in destinations else destinations[0],
            PlotPages(pdf),
            support / "algorithm-metrics-over-time.pdf",
            support / "algorithm-metrics-vs-goodput.pdf",
        )

        fig = page("3(b): Proposed congestion control algorithm", 5)
        prose(fig, text["Design"], 0.90, size=10, spacing=0.0165, bottom=0.06)
        fig.text(
            0.075,
            0.035,
            "AI helped with code, plots, checking, and drafting. A teammate collected the Linux/WSL2 measurements.",
            fontsize=8,
            family="serif",
        )
        pdf.savefig(fig)
        plt.close(fig)
