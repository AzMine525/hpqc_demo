"""Regression tests for timing evidence, delivery and failure accounting."""

from concurrent.futures import ThreadPoolExecutor
import csv
import io
import json
from pathlib import Path
import socket
import struct
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import psutil

from benchmark import run_experiment, workloads
from protocol.data_v2 import Acknowledgement, ReceivedData


class BenchmarkTests(unittest.TestCase):
    def test_summary_excludes_warmup_and_preserves_missing_values(self):
        labels = dict(workload="network", suite="ml-kem-768", payload_bytes=1024,
                      direction="client_to_server", metric="latency", unit="ns")
        rows = [dict(**labels, phase="measured", status="ok", value=n) for n in (1, 2, 3, 4)]
        rows.append(dict(**labels, phase="warmup", status="ok", value=999))
        rows.append(dict(**labels, phase="measured", status="unavailable", value=None))
        stats, = run_experiment.summary(rows)
        self.assertEqual((stats["n"], stats["unavailable"]), (4, 1))
        self.assertEqual((stats["mean"], stats["median"], stats["p95"]), (2.5, 2.5, 4))
        self.assertAlmostEqual(stats["sd_sample"], (5 / 3) ** 0.5)
        only_missing, = run_experiment.summary(rows[-1:])
        self.assertEqual(only_missing["n"], 0)
        self.assertIsNone(only_missing["mean"])
        singleton, = run_experiment.summary(rows[:1])
        self.assertIsNone(singleton["sd_sample"])

    def test_ack_requires_exact_payload_and_message_id(self):
        sender, receiver = Mock(), Mock()
        sent_id = bytes(16)
        sender.send_data.return_value = sent_id
        with ThreadPoolExecutor(1) as pool:
            for ack, data in (
                (Acknowledgement(sent_id), ReceivedData(sent_id, b"wrong")),
                (Acknowledgement(b"x" * 16), ReceivedData(sent_id, b"expected")),
            ):
                sender.receive.return_value, receiver.receive.return_value = ack, data
                with self.subTest(), self.assertRaises(workloads.BenchmarkError):
                    workloads.confirmed_rtt(pool, sender, receiver, b"expected")

    def test_failed_handshake_is_exported_as_failed_delivery(self):
        with patch.object(workloads, "DataChannel", side_effect=workloads.BenchmarkError):
            rows = run_experiment.collect(["ml-kem-768"], ("network",), 0, 1, 1.0, psutil.Process())
        statuses = [row for row in rows if row["metric"] == "trial"]
        self.assertEqual(len(statuses), 3)
        self.assertTrue(all(row["status"] == "failed" and row["error"] == "BenchmarkError"
                            for row in statuses))
        delivery = [row for row in rows if row["metric"] == "delivery_success"]
        self.assertEqual([row["value"] for row in delivery], [0] * 6)
        self.assertFalse(any(row["metric"] in ("goodput", "handshake") for row in rows))

    def test_retransmission_counts_availability(self):
        sock = Mock(spec=socket.socket)
        with patch.object(workloads.sys, "platform", "win32"):
            self.assertIsNone(workloads.tcp_retransmissions(sock))
            sock.getsockopt.assert_not_called()
        with patch.object(workloads.sys, "platform", "linux"), patch.object(
            workloads.socket, "TCP_INFO", 11, create=True,
        ):
            sock.getsockopt.return_value = bytes(100) + struct.pack("=I", 7)
            self.assertEqual(workloads.tcp_retransmissions(sock), 7)
            sock.getsockopt.return_value = bytes(100)
            self.assertIsNone(workloads.tcp_retransmissions(sock))
            sock.getsockopt.side_effect = OSError
            self.assertIsNone(workloads.tcp_retransmissions(sock))

    def test_cli_creates_csv_with_real_crypto_and_loopback_data(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            args = ["run_experiment", "--suite", "ml-kem-768", "--warmup", "1", "--trials", "2",
                    "--output", str(output)]
            with patch.object(sys, "argv", args), patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(run_experiment.main(), 0)
                with patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit):
                    run_experiment.main()
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual((manifest["attempts"], manifest["failures"]), (12, 0))
            with (output / "network_raw.csv").open(newline="", encoding="utf-8") as raw:
                rows = list(csv.DictReader(raw))
            wires = [r["value"] for r in rows if r["metric"] == "handshake_wire"]
            self.assertEqual(wires, ["2520"] * 9)
            delivery = [r["value"] for r in rows if r["metric"] == "delivery_success"]
            self.assertEqual(delivery, ["1"] * 18)
            with (output / "summary.csv").open(newline="", encoding="utf-8") as report:
                stats = list(csv.DictReader(report))
            timed = [r for r in stats if r["metric"] == "application_rtt"]
            self.assertEqual(len(timed), 6)
            self.assertTrue(all(r["n"] == "2" and float(r["mean"]) > 0 for r in timed))
            self.assertFalse(any(r["metric"] == "trial" for r in stats))
