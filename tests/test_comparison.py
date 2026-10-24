import json
import socket
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from client import ClientConfig, TestResult, data_connection
from comparison import load_run, preflight, run_comparison
from comparison_plots import build_report, percentile, run_statistics, plot_comparison
from destinations import Server, run_destinations
import matplotlib.pyplot as plt
from reviewed_report import build_reviewed_report
from dataclasses import replace

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / (
    "results/algorithm-comparisons/q3-test/tcp-traces/"
    "q3-test-d1-r1-cubic_dal.speedtest.clouvider.net_5200/"
    "tcp-samples.csv"
)
CFG = ClientConfig(15, 5, .5, 5, 3, 3)


class SocketSelectionTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(socket, "TCP_CONGESTION", 13, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_algorithm_is_set_and_checked_before_connect(self):
        sock = MagicMock()
        with patch("client.socket.getaddrinfo", return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 5201))
        ]), patch("client.socket.socket", return_value=sock), patch(
            "client.get_tcp_algorithm", return_value="reno"
        ):
            with data_connection("localhost", 5201, replace(CFG, algorithm="reno")):
                pass
        names = [call[0] for call in sock.mock_calls]
        self.assertLess(names.index("setsockopt"), names.index("connect"))
        sock.setsockopt.assert_called_once_with(socket.IPPROTO_TCP, socket.TCP_CONGESTION, b"reno")
        sock.__exit__.assert_called_once()

    def test_mismatch_never_connects(self):
        sock = MagicMock()
        with patch("client.socket.getaddrinfo", return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 5201))
        ]), patch("client.socket.socket", return_value=sock), patch(
            "client.get_tcp_algorithm", return_value="cubic"
        ):
            with self.assertRaises(OSError):
                with data_connection("localhost", 5201, replace(CFG, algorithm="bbr")):
                    pass
        sock.connect.assert_not_called()
        sock.close.assert_called_once()

    def test_unavailable_algorithm_fails_preflight(self):
        sock = MagicMock()
        sock.__enter__.return_value = sock
        sock.setsockopt.side_effect = OSError("unavailable")
        with patch("comparison.platform.system", return_value="Linux"), patch(
            "comparison.socket.socket", return_value=sock
        ):
            with self.assertRaisesRegex(SystemExit, "No algorithm was substituted"):
                preflight(["bbr"])


class ComparisonTests(unittest.TestCase):
    def test_weighted_goodput_matches_acknowledged_bytes(self):
        meta, samples = load_run(BASELINE)
        row = run_statistics({"repetition": 1}, (meta, samples))
        expected = sum(s.bytes_acked_delta for s in samples) / sum(s.interval for s in samples) * 8e-6
        self.assertAlmostEqual(row["goodput_weighted_mbps"], expected)
        self.assertEqual(percentile([0, 10], .95), 9.5)
        self.assertEqual(percentile([7], .95), 7)

    def test_failed_candidate_is_replaced_as_a_whole(self):
        meta, samples = load_run(BASELINE)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            servers = out / "servers.csv"
            servers.write_text("IP/HOST,PORT\nfirst,5201\nsecond,5201\n")
            args = Namespace(algorithms=["cubic", "reno", "bbr"], seed=422, servers=servers,
                             count=1, attempts=2, out_dir=out, repetitions=3, pause=.001)
            calls = []
            def runner(host, port, cfg, run_id):
                calls.append((host, cfg.algorithm, run_id))
                if len(calls) == 2:
                    return None
                return TestResult(replace(meta, host=host, port=port, algorithm=cfg.algorithm,
                                          run_id=run_id), samples, 1)
            with patch("comparison.preflight", return_value={"kernel": "test"}), patch(
                "comparison.try_run_test", side_effect=runner
            ), patch("comparison.time.sleep"), patch("comparison.analyze_manifest"):
                self.assertTrue(run_comparison(args, CFG, "test"))
            manifest = json.loads((out / "algorithm-comparisons/test/manifest.json").read_text())
            self.assertEqual(len(calls), 18)
            self.assertEqual(len(manifest["selected_destinations"]), 1)
            self.assertNotEqual(manifest["selected_destinations"][0], f"{calls[0][0]}:5201")
            self.assertEqual(sum(t["status"] == "failed" for t in manifest["tests"]), 1)
            for offset in (0, 9):
                for position in range(3):
                    self.assertEqual({calls[offset + rep * 3 + position][1] for rep in range(3)},
                                     {"cubic", "reno", "bbr"})
            self.assertTrue(all((out / "algorithm-comparisons/test" / t["csv"]).exists()
                                for t in manifest["tests"] if t["status"] == "ok"))
            self.assertTrue(all(Path(t["csv"]).parts[0] == "tcp-traces"
                                for t in manifest["tests"] if t["status"] == "ok"))

    def test_failed_destinations_create_output_and_reject_duplicate_run(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "missing" / "results"
            with patch("destinations.try_run_test", return_value=None) as runner:
                run_destinations([Server("unreachable.test", 5201)], 1, 1, CFG, "failed", out)
                self.assertGreater((out / "destination-tests/failed/reports/destination-goodput-statistics.pdf").stat().st_size, 100)
                with self.assertRaisesRegex(SystemExit, "Choose a fresh --run-id"):
                    run_destinations([Server("unreachable.test", 5201)], 1, 1, CFG, "failed", out)
                runner.assert_called_once()

    def test_offline_report_uses_saved_measurements(self):
        meta, samples = load_run(BASELINE)
        algorithms = ["cubic", "reno", "bbr"]
        runs = [({"repetition": repetition},
                 (replace(meta, algorithm=algorithm, run_id=f"fixture-{algorithm}-{repetition}"), samples))
                for algorithm in algorithms for repetition in (1, 2, 3)]
        manifest = {
            "run_id": "q3-test",
            "selected_destinations": [meta.destination()], "requested_destinations": 1,
            "representative": meta.destination(), "algorithms": algorithms,
            "repetitions": 3, "config": {"duration": meta.duration,
                                       "goodput_interval": meta.goodput_interval},
            "seed": 422, "environment": {"kernel": meta.kernel}, "order_method": "test fixture",
        }
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            build_report(manifest, runs, out)
            for name in ("reports/algorithm-comparison-report.pdf", "plots/algorithm-metrics-over-time.pdf",
                         "plots/algorithm-metrics-vs-goodput.pdf", "reports/per-test-statistics.csv",
                         "reports/destination-algorithm-statistics.csv"):
                self.assertGreater((out / name).stat().st_size, 100)
            self.assertIn("cubic", (out / "reports/algorithm-comparison-report.md").read_text())
            build_reviewed_report(manifest, runs, out)
            self.assertGreater((out / "reports/reviewed-algorithm-comparison.pdf").stat().st_size, 100)
            self.assertTrue((out / "plots/reviewed-report-figures/algorithm-metrics-over-time.pdf").exists())
            with patch("reviewed_report.PdfPages") as pdf:
                build_reviewed_report({**manifest, "run_id": "another-experiment"}, runs, out)
                pdf.assert_not_called()

    def test_common_axes_include_later_algorithms(self):
        meta, samples = load_run(BASELINE)
        runs = []
        for algorithm, window, rtt, goodput in (("cubic", 100, 10_000, 10),
                                                ("reno", 9000, 400_000, 200),
                                                ("bbr", 4000, 200_000, 100)):
            sample = replace(samples[0], goodput=goodput,
                             info={**samples[0].info, "snd_cwnd": window, "rtt": rtt})
            runs.append(({"repetition": 1}, (replace(meta, algorithm=algorithm), [sample])))
        figures = []
        original_close = plt.close
        def capture(fig):
            if hasattr(fig, "axes"):
                figures.append(fig)
            original_close(fig)
        with tempfile.TemporaryDirectory() as directory, patch(
            "comparison_plots.plt.close", side_effect=capture
        ):
            out = Path(directory)
            plot_comparison(runs, ["cubic", "reno", "bbr"], meta.destination(), MagicMock(),
                            out / "timeseries.pdf", out / "scatter.pdf")
        timeseries, scatter = figures
        self.assertGreaterEqual(timeseries.axes[0].get_ylim()[1], 9000)
        self.assertGreaterEqual(timeseries.axes[3].get_ylim()[1], 400)
        self.assertGreaterEqual(timeseries.axes[9].get_ylim()[1], 200)
        self.assertGreaterEqual(scatter.axes[0].get_xlim()[1], 9000)
        self.assertGreaterEqual(scatter.axes[3].get_xlim()[1], 400)
        self.assertGreaterEqual(scatter.axes[0].get_ylim()[1], 200)
        self.assertEqual(timeseries.axes[0].get_ylim(), timeseries.axes[2].get_ylim())
        self.assertEqual(scatter.axes[0].get_xlim(), scatter.axes[2].get_xlim())

    def test_no_complete_group_produces_no_comparison_claim(self):
        run = load_run(BASELINE)
        manifest = {
            "selected_destinations": [], "requested_destinations": 1, "representative": None,
            "algorithms": ["cubic", "reno", "bbr"], "repetitions": 3,
            "config": {"duration": 15, "goodput_interval": .5}, "seed": 422,
            "environment": {"kernel": run[0].kernel}, "order_method": "test",
        }
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            build_report(manifest, [({"repetition": 1}, run)], out)
            self.assertIn("no measured algorithm comparison", (out / "reports/algorithm-comparison-report.md").read_text())
            self.assertFalse((out / "reports/destination-algorithm-statistics.csv").exists())


if __name__ == "__main__":
    unittest.main()
