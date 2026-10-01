import logging

from cli import create_parser
from client import ClientConfig, try_run_test
from destinations import load_servers, run_destinations


def main() -> None:
    args = create_parser().parse_args()
    logging.basicConfig(level=logging.DEBUG, format="%(message)s")

    client_config = ClientConfig(
        duration=args.time,
        print_interval=args.print_interval,
        connect_timeout=args.connect_timeout,
        control_timeout=args.control_timeout,
        data_timeout=args.data_timeout,
    )

    if args.command == "test":
        if not try_run_test(args.host, args.port, client_config):
            raise SystemExit(1)

    elif args.command == "destinations":
        run_destinations(load_servers(args.servers), args.count, args.attempts, client_config)


if __name__ == "__main__":
    main()
