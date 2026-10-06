import csv
import random
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean, median, quantiles
from textwrap import fill

import matplotlib
from matplotlib.transforms import Bbox

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle

from client import ClientConfig, TestResult, try_run_test
from log_utils import log_message

GRAPHS_PATH = "goodput-graphs.pdf"
SUMMARY_TABLE_PATH = "goodput-summary.pdf"


@dataclass
class Server:
    host: str
    port: int

    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"


def load_servers(filepath: Path) -> list[Server]:
    servers: list[Server] = []

    with open(filepath) as f:
        reader = csv.DictReader(f)

        for row in reader:
            port = int(row["PORT"].split("-")[0])
            servers.append(Server(row["IP/HOST"], port))

    return servers


def plot_destinations(servers: list[tuple[Server, TestResult]]) -> None:
    num_dest = len(servers)

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

    for ax, (server, test_result) in zip(axes.flat[:num_dest], servers, strict=True):
        max_goodput = max(max_goodput, max([sample.value for sample in test_result.goodput]))

        x, y = zip(*test_result.goodput, strict=True)
        ax.plot(x, y, linewidth=1.5)

        ax.set_title(f"{server.endpoint()}\n{test_result.algorithm}", fontsize=11)
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

    fig.savefig(GRAPHS_PATH, format="pdf", bbox_inches="tight")
    plt.close(fig)

    log_message("destinations", f"Plot saved to {GRAPHS_PATH}")


def save_summary_table(servers: list[tuple[Server, TestResult]]) -> None:
    percentile = 95
    rows: list[list[str]] = []

    for server, test_result in servers:
        values = [sample.value for sample in test_result.goodput]
        quant = quantiles(values, n=100, method="inclusive")
        stats = (min(values), median(values), fmean(values), quant[percentile - 1])
        stats_fmt = [f"{value:,.2f}" for value in stats]
        rows.append([fill(server.endpoint(), width=48), test_result.algorithm, *stats_fmt])

    rows_per_page = 15
    top_space = 1.1
    bottom_space = 0.5
    text_spacing = 0.4
    left_margin = 0.04
    right_edge = 1 - left_margin
    column_widths = (0.40, 0.10, 0.10, 0.11, 0.10, 0.10)
    table_width = sum(column_widths)

    num_pages = max(1, (len(rows) + rows_per_page - 1) // rows_per_page)

    with PdfPages(SUMMARY_TABLE_PATH) as pdf:
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
                color="#20344b",
            )
            fig.text(
                left_margin,
                1 - 2 * text_spacing / page_height,
                f"{len(rows)} destinations | Throughput in Mbit/s",
                fontsize=11,
                color="#596779",
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
                        cell.set_facecolor("#20344b")
                        text.set_color("white")
                        text.set_fontweight("bold")
                    else:
                        cell.set_facecolor("#edf2f7" if row % 2 else "white")
                        text.set_color("#20344b")
            else:
                ax.text(0, 0.5, "No successful tests to summarize.", fontsize=12, color="#596779")

            fig.text(
                right_edge,
                0.18 / page_height,
                f"{page + 1} / {num_pages}",
                ha="right",
                fontsize=9,
                color="#596779",
            )

            pdf.savefig(fig)
            plt.close(fig)

    log_message("destinations", f"Summary saved to {SUMMARY_TABLE_PATH}")


def run_destinations(servers: list[Server], count: int, attempts: int, cfg: ClientConfig) -> None:
    shuffled_servers = servers.copy()
    random.shuffle(shuffled_servers)
    server_idx = 0

    tested_servers: list[tuple[Server, TestResult]] = []

    for i in range(count):
        curr_attempt = 1

        while server_idx < len(shuffled_servers):
            server = shuffled_servers[server_idx]
            attempt_label = f"Server {i + 1}/{count} | attempt {curr_attempt}/{attempts}"
            test_result = try_run_test(server.host, server.port, cfg, quiet=True)

            if test_result is not None:
                log_message("destinations", f"{attempt_label} | passed: {server.endpoint()}")
                tested_servers.append((server, test_result))

                break

            if curr_attempt == attempts:
                log_message("destinations", f"{attempt_label} | failed; limit reached")
                break

            log_message("destinations", f"{attempt_label} | failed; trying next server")

            curr_attempt += 1
            server_idx += 1

        if server_idx == len(shuffled_servers):
            break

        server_idx += 1

    log_message("destinations", f"Selected {len(tested_servers)}/{count} servers")

    save_summary_table(tested_servers)
    plot_destinations(tested_servers)
