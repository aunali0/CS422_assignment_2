import argparse
from math import isfinite
from pathlib import Path


def number(kind: type[int] | type[float], value: str) -> int | float:
    try:
        result = kind(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"must be {'an integer' if kind is int else 'a number'}"
        ) from None
    if not isfinite(result):
        raise argparse.ArgumentTypeError("must be finite")
    return result


def positive_int_type(value: str) -> int:
    result = int(number(int, value))
    if result <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return result


def positive_float_type(value: str) -> float:
    result = float(number(float, value))
    if result <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return result


def port_type(value: str) -> int:
    port = int(number(int, value))
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535 (inclusive)")
    return port


def add_client_args(parser: argparse.ArgumentParser) -> None:
    client = parser.add_argument_group("client")
    client.add_argument(
        "--algorithm", default=None, help="Data socket congestion control algorithm"
    )
    client.add_argument(
        "-t", "--time", type=positive_int_type, default=60, metavar="SECONDS", help="Test duration"
    )
    client.add_argument(
        "-i",
        "--print-interval",
        type=positive_float_type,
        default=5.0,
        metavar="SECONDS",
        help="How often test progress is printed",
    )
    client.add_argument(
        "-g",
        "--goodput-interval",
        type=positive_float_type,
        default=1,
        metavar="SECONDS",
        help="How often goodput is measured during test",
    )
    client.add_argument(
        "--connect-timeout",
        type=positive_float_type,
        default=5.0,
        metavar="SECONDS",
        help="Timeout for establishing connection with server",
    )
    client.add_argument(
        "--control-timeout",
        type=positive_float_type,
        default=3.0,
        metavar="SECONDS",
        help="Timeout for communicating over control socket",
    )
    client.add_argument(
        "--data-timeout",
        type=positive_float_type,
        default=3.0,
        metavar="SECONDS",
        help="Timeout for communicating over data socket",
    )

    output = parser.add_argument_group("output")
    output.add_argument(
        "-o",
        "--out-dir",
        type=Path,
        default=Path("results"),
        metavar="DIR",
        help="Directory for raw measurements and plots",
    )
    output.add_argument(
        "--run-id",
        default=None,
        metavar="ID",
        help="Run identifier recorded in the output (default: UTC timestamp)",
    )


def add_analyze_command(commands):
    analyze = commands.add_parser(
        "analyze", help="Rebuild plots, tables, and reports from saved measurements (offline)"
    )
    analyze.add_argument(
        "path",
        type=Path,
        help="A run directory under results/, or a comparison's manifest.json",
    )


def add_compare_command(commands):
    compare = commands.add_parser(
        "compare",
        help="Compare congestion control algorithms with repeated runs on the same destinations",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    compare.add_argument(
        "-s", "--servers", type=Path, required=True, metavar="CSV", help="iPerf3 server list"
    )
    compare.add_argument(
        "-c", "--count", type=positive_int_type, default=10, help="Number of destinations"
    )
    compare.add_argument(
        "-a",
        "--attempts",
        type=positive_int_type,
        default=3,
        help="Maximum candidate destinations per requested destination",
    )
    compare.add_argument(
        "-r",
        "--repetitions",
        type=positive_int_type,
        default=3,
        help="Runs per algorithm and destination",
    )
    compare.add_argument(
        "--algorithms", nargs="+", default=["cubic", "reno", "bbr"], help="Algorithms to compare"
    )
    compare.add_argument(
        "--seed", type=int, default=422, help="Seed for destination and order shuffling"
    )
    compare.add_argument(
        "--pause", type=positive_float_type, default=2, help="Seconds between tests"
    )
    add_client_args(compare)


def add_destinations_command(commands):
    destinations = commands.add_parser(
        "destinations",
        help="Run a TCP upload test against multiple, randomly-selected iPerf3 servers",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    destinations.add_argument(
        "-s",
        "--servers",
        type=Path,
        required=True,
        metavar="CSV",
        help="Path to CSV file containing iPerf3 servers",
    )
    destinations.add_argument(
        "-c", "--count", type=positive_int_type, default=10, help="Number of servers"
    )
    destinations.add_argument(
        "-a",
        "--attempts",
        type=positive_int_type,
        default=3,
        help="Maximum attempts per destination, including the first server",
    )
    add_client_args(destinations)


def add_test_command(commands):
    test = commands.add_parser(
        "test",
        help="Run a TCP upload test against an iPerf3 server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    server = test.add_argument_group("server")
    server.add_argument("-s", "--host", required=True, help="Server hostname or IP address")
    server.add_argument("-p", "--port", type=port_type, default=5201, help="Server TCP port")

    add_client_args(test)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CLI for CS422 Assignment 2")
    commands = parser.add_subparsers(dest="command", required=True)

    add_test_command(commands)
    add_destinations_command(commands)
    add_compare_command(commands)
    add_analyze_command(commands)

    return parser
