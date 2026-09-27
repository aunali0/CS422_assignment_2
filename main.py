import argparse
import socket
import time


def to_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be an integer")


def port_type(value: str) -> int:
    port = to_int(value)

    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535 (inclusive)")

    return port


def positive_int_type(value: str) -> int:
    num = to_int(value)

    if num <= 0:
        raise argparse.ArgumentTypeError("must be positive")

    return num


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CLI for CS422 Assignment 2")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser(
        "run",
        help="Run a TCP client that connects to an iPERF3 server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    dest = run.add_argument_group("destination")
    dest.add_argument(
        "--host", 
        required=True, 
        help="Server hostname or IP address"
    )
    dest.add_argument(
        "--port", 
        type=port_type, 
        default=5201, 
        help="Server TCP port"
    )

    experiment = run.add_argument_group("experiment")
    experiment.add_argument(
        "--duration",
        type=positive_int_type,
        default=5,
        metavar="SECONDS",
        help="Experiment duration in seconds"
    )

    timeouts = run.add_argument_group("timeouts")
    timeouts.add_argument(
        "--connect-timeout",
        type=positive_int_type,
        default=5,
        metavar="SECONDS",
        help="Timeout in seconds for establishing a connection with server",
    )
    timeouts.add_argument(
        "--response-timeout",
        type=positive_int_type,
        default=10,
        metavar="SECONDS",
        help="Timeout in seconds for server response after successful connection",
    )

    return parser


def run_client(
        host: str, 
        port: int, 
        duration: int, 
        connect_timeout: int, 
        response_timeout: int
):  
    with socket.create_connection((host, port), timeout=connect_timeout) as sock:
        end_time = time.monotonic() + duration

        while (time_left := end_time - time.monotonic()) > 0:
            sock.settimeout(min(time_left, response_timeout))


def main():
    args = create_parser().parse_args()

    if args.command == "run":
        run_client(
            args.host, 
            args.port, 
            args.duration, 
            args.connect_timeout,
            args.response_timeout
        )


if __name__ == "__main__":
    main()
