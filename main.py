import logging
from datetime import UTC, datetime

from cli import create_parser
from client import ClientConfig, try_run_test
from destinations import load_servers, run_destinations
from measurement import save_run
from plots import save_run_plots


def main() -> None:
    logging.basicConfig(level=logging.DEBUG, format="%(message)s")
    logging.getLogger("matplotlib").setLevel(logging.WARNING)

    args = create_parser().parse_args()

    if args.command == "analyze":
        from comparison import analyze_manifest
        analyze_manifest(args.manifest)
        return

    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    client_config = ClientConfig(
        duration=args.time,
        print_interval=args.print_interval,
        goodput_interval=args.goodput_interval,
        connect_timeout=args.connect_timeout,
        control_timeout=args.control_timeout,
        data_timeout=args.data_timeout,
        algorithm=args.algorithm,
    )

    if args.command == "compare":
        from comparison import run_comparison
        if args.algorithm:
            raise SystemExit("Use --algorithms with compare")
        complete = run_comparison(args, client_config, run_id)
        if not complete:
            raise SystemExit(1)
    elif args.command == "test":
        result = try_run_test(args.host, args.port, client_config, run_id)

        if result is None:
            raise SystemExit(1)

        save_run(result.metadata, result.samples, args.out_dir)
        save_run_plots(result.metadata, result.samples, args.out_dir)

    elif args.command == "destinations":
        run_destinations(
            load_servers(args.servers),
            args.count,
            args.attempts,
            client_config,
            run_id,
            args.out_dir,
        )


if __name__ == "__main__":
    main()
