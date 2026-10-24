import logging
from datetime import UTC, datetime
from pathlib import Path

from cli import create_parser
from client import ClientConfig, try_run_test
from comparison import analyze_manifest, run_comparison
from destinations import load_servers, run_destinations
from log_utils import log_message
from measurement import create_run_directory, load_runs, save_run
from plots import save_destination_outputs


def analyze(path: Path) -> None:
    """Regenerate plots, tables, and reports for a saved run directory without the network."""
    run_dir = path.parent if path.is_file() else path

    if (run_dir / "manifest.json").exists():
        analyze_manifest(run_dir / "manifest.json")
        return

    runs = load_runs(run_dir)
    if not runs:
        raise SystemExit(f"No saved traces under {run_dir / 'tcp-traces'}")
    save_destination_outputs(runs, run_dir)


def main() -> None:
    logging.basicConfig(level=logging.DEBUG, format="%(message)s")
    logging.getLogger("matplotlib").setLevel(logging.WARNING)

    args = create_parser().parse_args()

    if args.command == "analyze":
        analyze(args.path)
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

    if args.command == "test":
        out = create_run_directory(args.out_dir, run_id, "single-server-tests")
        result = try_run_test(args.host, args.port, client_config, run_id)

        if result is None:
            raise SystemExit(1)

        save_run(result.metadata, result.samples, out / "tcp-traces" / result.metadata.slug())
        save_destination_outputs([(result.metadata, result.samples)], out)

    elif args.command == "destinations":
        run_destinations(
            load_servers(args.servers),
            args.count,
            args.attempts,
            client_config,
            run_id,
            args.out_dir,
        )

    elif args.command == "compare":
        if args.algorithm:
            raise SystemExit("Use --algorithms with compare")

        if not run_comparison(args, client_config, run_id):
            raise SystemExit(1)

    log_message("test", f"Run ID: {run_id}")


if __name__ == "__main__":
    main()
