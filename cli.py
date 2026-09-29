import argparse
from pathlib import Path


def to_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be an integer") from None


def to_float(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a float") from None


def port_type(value: str) -> int:
    port = to_int(value)

    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535 (inclusive)")

    return port


def check_positive[T: (int, float)](num: T) -> T:
    if num <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return num


def positive_int_type(value: str) -> int:
    return check_positive(to_int(value))


def positive_float_type(value: str) -> float:
    return check_positive(to_float(value))


def add_test_args(parser: argparse.ArgumentParser) -> None:
    settings = parser.add_argument_group("settings")
    settings.add_argument(
        "-t", "--time", type=positive_int_type, default=10, metavar="SECONDS", help="Test duration"
    )

    settings.add_argument(
        "-i",
        "--print-interval",
        type=positive_float_type,
        default=1.0,
        metavar="SECONDS",
        help="How often test progress is printed",
    )

    timeouts = parser.add_argument_group("timeouts")
    timeouts.add_argument(
        "--connect-timeout",
        type=positive_float_type,
        default=5.0,
        metavar="SECONDS",
        help="Timeout for establishing connection with server",
    )
    timeouts.add_argument(
        "--control-timeout",
        type=positive_float_type,
        default=3.0,
        metavar="SECONDS",
        help="Timeout for communicating over control socket",
    )
    timeouts.add_argument(
        "--data-timeout",
        type=positive_float_type,
        default=3.0,
        metavar="SECONDS",
        help="Timeout for communicating over data socket",
    )


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CLI for CS422 Assignment 2")
    commands = parser.add_subparsers(dest="command", required=True)

    test = commands.add_parser(
        "test",
        help="Run a TCP upload test against an iPerf3 server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    server = test.add_argument_group("server")
    server.add_argument("-s", "--host", required=True, help="Server hostname or IP address")
    server.add_argument("-p", "--port", type=port_type, default=5201, help="Server TCP port")

    add_test_args(test)

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
        help="Number of replacement attempts when server rate-limits or rejects test",
    )

    add_test_args(destinations)

    return parser
