from cli import create_parser
from client import run_test
from destinations import run_tests_with_destinations


def main() -> None:
    args = create_parser().parse_args()

    if args.command == "test":
        run_test(
            host=args.host,
            port=args.port,
            duration=args.time,
            print_interval=args.print_interval,
            connect_timeout=args.connect_timeout,
            control_timeout=args.control_timeout,
            data_timeout=args.data_timeout,
        )
    elif args.command == "destinations":
        run_tests_with_destinations(
            servers_file=args.servers,
            duration=args.time,
            print_interval=args.print_interval,
            connect_timeout=args.connect_timeout,
            control_timeout=args.control_timeout,
            data_timeout=args.data_timeout,
        )


if __name__ == "__main__":
    main()
