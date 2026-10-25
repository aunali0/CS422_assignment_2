# Builds the submission PDF from REPORT.md plus the saved measurements.
#
# REPORT.md is ordinary Markdown with three extensions, so all prose lives in one file:
#   ![Caption](figure:NAME)   a figure generated here from saved data (see FIGURES)
#   {{table:NAME}}            a table generated here from saved data (see TABLES)
#   [label](code:FILE#TEXT)   a GitHub link to the first line of FILE containing TEXT,
#                             pinned to the current commit, so line numbers never go stale
# Supported Markdown: #/##/### headings, paragraphs, "- " bullets, ``` code blocks,
# | pipe | tables |, **bold**, *italic*, `code`, and [links](https://...).

import re
import subprocess
from collections import Counter, defaultdict
from html import escape
from pathlib import Path
from statistics import fmean, stdev

import matplotlib
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from comparison import load_comparison
from comparison_plots import matched_destinations, plot_comparison, run_statistics
from log_utils import log_message
from measurement import Run, load_runs
from plots import SUMMARY_COLUMNS, plot_destinations, plot_scatter, plot_time_series, summary_rows
from tcp_info import TCP_INFO_FIELDS

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "REPORT.md"
OUTPUT = ROOT / "report" / "CS422-Assignment-2-Report.pdf"
FIGURES_DIR = ROOT / "report" / "figures"
REPOSITORY = "https://github.com/aunali0/CS422_assignment_2"

# The saved experiments the report describes.
COMPARISON_DIR = ROOT / "results" / "algorithm-comparisons" / "q3-test"
Q2_DIR = ROOT / "results" / "single-server-tests" / "20261018T035817Z"

ALGORITHMS = ["cubic", "reno", "bbr"]
# tcp_info fields this project relies on, shown in the Q2(a) decoding table.
DECODED_FIELDS = (
    "snd_mss", "unacked", "lost", "rtt", "rttvar", "snd_ssthresh", "snd_cwnd", "total_retrans",
    "pacing_rate", "bytes_acked", "notsent_bytes", "min_rtt", "data_segs_out", "delivery_rate",
    "delivered", "bytes_retrans",
)  # fmt: skip


# ---------------------------------------------------------------- saved data


class Data:
    def __init__(self) -> None:
        self.manifest, self.tests = load_comparison(COMPARISON_DIR / "manifest.json")
        self.matched = matched_destinations(self.manifest, self.tests)
        self.comparison_runs: list[Run] = [run for _, run in self.tests]
        self.q2_meta, self.q2_samples = load_runs(Q2_DIR)[0]


# ---------------------------------------------------------------- figures


def figure_q1_goodput(data: Data, path: Path) -> None:
    plot_destinations(data.comparison_runs, path)


def figure_q2_time_series(data: Data, path: Path) -> None:
    plot_time_series(data.q2_meta, data.q2_samples, path)


def figure_q2_scatter(data: Data, path: Path) -> None:
    plot_scatter(data.q2_meta, data.q2_samples, path)


def figure_q3_time_series(data: Data, path: Path) -> None:
    plot_comparison(data.tests, ALGORITHMS, data.manifest["representative"], path, None)


def figure_q3_scatter(data: Data, path: Path) -> None:
    plot_comparison(data.tests, ALGORITHMS, data.manifest["representative"], None, path)


FIGURES = {
    "q1_goodput": figure_q1_goodput,
    "q2_time_series": figure_q2_time_series,
    "q2_scatter": figure_q2_scatter,
    "q3_time_series": figure_q3_time_series,
    "q3_scatter": figure_q3_scatter,
}


# ---------------------------------------------------------------- tables


def table_q1_summary(data: Data) -> list[list[str]]:
    # Q1(c): min / median / mean / P95 per destination and algorithm, repetitions pooled.
    return [SUMMARY_COLUMNS, *summary_rows(data.comparison_runs)]


def table_q1_attempts(data: Data) -> list[list[str]]:
    # Q1(b): every candidate destination, its test outcomes, and the logged failure causes.
    causes: dict[str, Counter[str]] = defaultdict(Counter)
    log = (COMPARISON_DIR / "experiment.log").read_text()
    for destination, error in re.findall(r"\[error\] (\S+) \| (\w+(?:: Unexpected state: \w+)?)", log):
        causes[destination][error.replace("ConnectionError: Unexpected state: ", "")] += 1

    rows = [["Candidate (in order)", "OK", "Failed", "Failure causes", "Used"]]
    outcomes: dict[str, Counter[str]] = {}
    for test in data.manifest["tests"]:
        outcomes.setdefault(test["destination"], Counter())[test["status"]] += 1
    for destination, counts in outcomes.items():
        cause = ", ".join(f"{name} ×{n}" for name, n in causes[destination].most_common())
        used = "yes" if destination in data.matched else "no (incomplete)"
        rows.append([destination, str(counts["ok"]), str(counts["failed"]), cause or "–", used])
    return rows


def table_tcp_info_layout(data: Data) -> list[list[str]]:
    # Q2(a): byte offsets of the decoded fields, computed from the same table the decoder uses.
    rows = [["Field", "Offset (bytes)", "Format", "Unit"]]
    offset = 0
    for name, fmt, unit in TCP_INFO_FIELDS:
        if name in DECODED_FIELDS:
            rows.append([f"tcpi_{name}", str(offset), {"B": "u8", "H": "u16", "I": "u32", "Q": "u64"}[fmt], unit])
        offset += {"B": 1, "H": 2, "I": 4, "Q": 8}[fmt]
    return rows


def table_q3_results(data: Data) -> list[list[str]]:
    # Q3(a): per destination and algorithm, mean of the run goodputs ± sample SD across runs.
    rows = [["Destination", "Algorithm", "Goodput (Mbit/s)", "Mean RTT (ms)", "Retrans. (segs)"]]
    stats = [run_statistics(test, run) for test, run in data.tests if run[0].destination() in data.matched]
    for destination in data.matched:
        for algorithm in ALGORITHMS:
            group = [r for r in stats if r["destination"] == destination and r["algorithm"] == algorithm]
            goodput = [r["goodput_weighted_mbps"] for r in group]
            rows.append([
                destination,
                algorithm,
                f"{fmean(goodput):.2f} ± {stdev(goodput):.2f}",
                f"{fmean(r['rtt_mean_ms'] for r in group):.2f}",
                str(sum(r["retransmitted_segments"] for r in group)),
            ])  # fmt: skip
    return rows


def table_q3_order(data: Data) -> list[list[str]]:
    # Q3(a): the exact test order, read from the manifest.
    rows = [["Destination", "Repetition 1", "Repetition 2", "Repetition 3"]]
    order: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    for test in data.manifest["tests"]:
        if test["destination"] in data.matched:
            order[test["destination"]][test["repetition"]].append(test["requested_algorithm"])
    for destination in data.matched:
        rows.append([destination, *(" → ".join(order[destination][r]) for r in (1, 2, 3))])
    return rows


TABLES = {
    "q1_attempts": table_q1_attempts,
    "q1_summary": table_q1_summary,
    "tcp_info_layout": table_tcp_info_layout,
    "q3_order": table_q3_order,
    "q3_results": table_q3_results,
}


# ---------------------------------------------------------------- markdown -> PDF


def current_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout.strip()  # fmt: skip
    except (OSError, subprocess.CalledProcessError):
        return "main"


def code_link(target: str, commit: str) -> str:
    """'client.py#def run_test' -> GitHub URL of the first line containing 'def run_test'."""
    file, _, text = target.partition("#")
    lines = (ROOT / file).read_text().splitlines()
    number = next((i for i, line in enumerate(lines, 1) if text in line), None)
    if number is None:
        raise ValueError(f"REPORT.md links to '{text}', which is not in {file}")
    return f"{REPOSITORY}/blob/{commit}/{file}#L{number}"


def inline(text: str, commit: str) -> str:
    """Markdown inline syntax -> ReportLab paragraph markup."""
    code_spans: list[str] = []

    def stash(match: re.Match) -> str:
        code_spans.append(f'<font face="Mono" size="8.5">{escape(match[1])}</font>')
        return f"\x00{len(code_spans) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = escape(text, quote=False)

    def link(match: re.Match) -> str:
        url = code_link(match[2][5:], commit) if match[2].startswith("code:") else match[2]
        return f'<link href="{escape(url)}" color="#1f5fa8">{match[1]}</link>'

    text = re.sub(r"\[([^\]]+)\]\((code:[^)]+|[^)\s]+)\)", link, text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: code_spans[int(m[1])], text)


def register_fonts() -> None:
    # Embed matplotlib's STIX (a Times look-alike) and DejaVu Sans Mono: unlike the built-in
    # PDF fonts they cover symbols such as Δ, β, ≈, −, and →.
    fonts = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    for name, file in (("Serif", "STIXGeneral"), ("Serif-Bold", "STIXGeneralBol"),
                       ("Serif-Italic", "STIXGeneralItalic"), ("Serif-BoldItalic", "STIXGeneralBolIta"),
                       ("Mono", "DejaVuSansMono")):  # fmt: skip
        pdfmetrics.registerFont(TTFont(name, fonts / f"{file}.ttf"))
    pdfmetrics.registerFontFamily("Serif", normal="Serif", bold="Serif-Bold",
                                  italic="Serif-Italic", boldItalic="Serif-BoldItalic")  # fmt: skip


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=base["BodyText"], fontName="Serif", fontSize=10.5,
                          leading=13.8, spaceAfter=6)  # fmt: skip
    return {
        "title": ParagraphStyle("title", parent=body, fontName="Serif-Bold", fontSize=18,
                                leading=22, alignment=TA_CENTER, spaceAfter=4),
        "subtitle": ParagraphStyle("subtitle", parent=body, fontSize=12, alignment=TA_CENTER,
                                   spaceAfter=12),
        "h2": ParagraphStyle("h2", parent=body, fontName="Serif-Bold", fontSize=14, leading=17,
                             spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#20344b")),
        "h3": ParagraphStyle("h3", parent=body, fontName="Serif-Bold", fontSize=11.5, leading=14,
                             spaceBefore=8, spaceAfter=4),
        "body": body,
        "cell": ParagraphStyle("cell", parent=body, fontSize=8.5, leading=10.5, spaceAfter=0),
        "caption": ParagraphStyle("caption", parent=body, fontSize=9, leading=11.5,
                                  textColor=colors.HexColor("#3b4654"), spaceAfter=10),
        "code": ParagraphStyle("code", parent=body, fontName="Mono", fontSize=8.3, leading=10.2,
                               leftIndent=8, backColor=colors.HexColor("#f4f6f8"), borderPadding=5,
                               spaceBefore=4, spaceAfter=10),
    }  # fmt: skip


def make_table(rows: list[list[str]], st: dict, commit: str, width: float) -> Table:
    cells = [[Paragraph(inline(c, commit) if r else f"<b>{escape(c)}</b>", st["cell"]) for c in row]
             for r, row in enumerate(rows)]  # fmt: skip
    table = Table(cells, repeatRows=1, hAlign="LEFT", colWidths=column_widths(rows, width))
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e3e8ef")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fa")]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#8a96a3")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))  # fmt: skip
    return table


def column_widths(rows: list[list[str]], width: float) -> list[float]:
    # Wide enough for each column's longest word, then shared by content length (capped),
    # so short columns never wrap mid-word and long text columns take the remaining space.
    def plain(cell: str) -> str:
        return re.sub(r"\]\(.*?\)|[*`\[]", "", cell)

    weights = []
    for i in range(len(rows[0])):
        cells = [plain(row[i]) for row in rows]
        longest_word = max(len(word) for cell in cells for word in cell.split() or [""])
        weights.append(max(longest_word + 3, min(max(map(len, cells)), 40)))
    return [width * w / sum(weights) for w in weights]


def make_figure(path: Path, caption: str, st: dict, commit: str, frame_w: float, frame_h: float):
    image = Image(str(path))
    # At most ~3/4 of a page tall, so a figure can share its page with surrounding text.
    scale = min(frame_w / image.imageWidth, 0.74 * frame_h / image.imageHeight)
    image.drawWidth, image.drawHeight = image.imageWidth * scale, image.imageHeight * scale
    return KeepTogether([image, Spacer(1, 4), Paragraph(inline(caption, commit), st["caption"])])


def parse_blocks(markdown: str) -> list[tuple[str, object]]:
    blocks: list[tuple[str, object]] = []
    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line.startswith("```"):
            end = next(j for j in range(i + 1, len(lines)) if lines[j].startswith("```"))
            blocks.append(("code", "\n".join(lines[i + 1 : end])))
            i = end + 1
        elif m := re.match(r"(#{1,3}) (.*)", line):
            blocks.append((f"h{len(m[1])}", m[2]))
            i += 1
        elif m := re.fullmatch(r"!\[(.*)\]\(figure:(\w+)\)", line.strip()):
            blocks.append(("figure", (m[2], m[1])))
            i += 1
        elif m := re.fullmatch(r"\{\{table:(\w+)\}\}", line.strip()):
            blocks.append(("data_table", m[1]))
            i += 1
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            blocks.append(("table", rows))
        elif line.startswith("- "):
            items = []
            while i < len(lines) and (lines[i].startswith("- ") or lines[i].startswith("  ")):
                if lines[i].startswith("- "):
                    items.append(lines[i][2:])
                else:
                    items[-1] += " " + lines[i].strip()
                i += 1
            blocks.append(("list", items))
        else:
            text = []
            while i < len(lines) and lines[i].strip() and not re.match(r"(#|```|- |\||!\[|\{\{)", lines[i]):
                text.append(lines[i].strip())
                i += 1
            blocks.append(("p", " ".join(text)))
    return blocks


def build_report(output: Path = OUTPUT) -> Path:
    matplotlib.rcParams["savefig.dpi"] = 200
    register_fonts()
    data = Data()
    commit = current_commit()
    st = styles()

    doc = SimpleDocTemplate(str(output), pagesize=letter, title="CS 422 Assignment 2",
                            leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.7 * inch)  # fmt: skip
    output.parent.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    story = []
    for kind, value in parse_blocks(SOURCE.read_text()):
        if kind == "h1":
            title, _, subtitle = value.partition(" — ")
            story += [Paragraph(inline(title, commit), st["title"]),
                      Paragraph(inline(subtitle, commit), st["subtitle"])]  # fmt: skip
        elif kind in ("h2", "h3"):
            story.append(Paragraph(inline(value, commit), st[kind]))
        elif kind == "p":
            story.append(Paragraph(inline(value, commit), st["body"]))
        elif kind == "list":
            story.append(ListFlowable(
                [ListItem(Paragraph(inline(item, commit), st["body"]), leftIndent=14) for item in value],
                bulletType="bullet", start="•", leftIndent=14,
            ))  # fmt: skip
        elif kind == "code":
            story.append(Preformatted(value, st["code"]))
        elif kind == "table":
            story += [make_table(value, st, commit, doc.width), Spacer(1, 8)]
        elif kind == "data_table":
            story += [make_table(TABLES[value](data), st, commit, doc.width), Spacer(1, 8)]
        elif kind == "figure":
            name, caption = value
            path = FIGURES_DIR / f"{name}.png"
            FIGURES[name](data, path)
            story.append(make_figure(path, caption, st, commit, doc.width, doc.height))

    def page_number(canvas, document) -> None:
        canvas.setFont("Serif", 9)
        canvas.drawRightString(letter[0] - 0.8 * inch, 0.45 * inch, str(document.page))

    doc.build(story, onFirstPage=page_number, onLaterPages=page_number)
    log_message("test", f"Report saved to {output} (code links pinned to commit {commit})")
    return output
