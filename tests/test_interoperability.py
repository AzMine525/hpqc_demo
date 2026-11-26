"""Run both endpoint roles over TCP loopback with real KEM and AES operations."""

import os
from hashlib import sha256
from pathlib import Path
from queue import Empty, Queue
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import time
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT.parent / "hpqc_demo_baselines" / "prototype-original-20261126.zip"
BASELINE_CHAT_SHA256 = "40ab14ec37aef318de299603efa1511d86ae1d1c342a36347861cf99f8b792a1"
TIMEOUT = 10


class Endpoint:
    """Drive the real CLI over pipes and wait for its receive output."""

    def __init__(self, *command, port):
        self.lines = Queue()
        self.output = []
        self.process = subprocess.Popen(
            [sys.executable, "-B", "-u", *map(str, command), "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        self.reader = Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        for line in self.process.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def wait_for(self, text):
        deadline = time.monotonic() + TIMEOUT
        while True:
            try:
                line = self.lines.get(timeout=max(0, deadline - time.monotonic()))
            except Empty:
                raise AssertionError(f"Timed out awaiting {text!r}. Output: {self.output!r}") from None
            if line is None:
                raise AssertionError(f"Process ended before {text!r}. Output: {self.output!r}")
            self.output.append(line)
            if text in line:
                return line

    def send(self, message):
        self.process.stdin.write(message + "\n")
        self.process.stdin.flush()

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=TIMEOUT)
        self.reader.join(timeout=TIMEOUT)
        self.process.stdin.close()
        self.process.stdout.close()


class InteroperabilityTests(unittest.TestCase):
    def exchange(self, server_command, client_command):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        server = Endpoint(*server_command, port=port)
        self.addCleanup(server.close)
        server.wait_for(f"Menunggu koneksi pada 127.0.0.1:{port}")
        client = Endpoint(*client_command, port=port)
        self.addCleanup(client.close)

        server_fingerprint = server.wait_for("SHA256 fingerprint public key server:").split()[-1]
        client_fingerprint = client.wait_for("SHA256 fingerprint public key diterima:").split()[-1]
        self.assertRegex(server_fingerprint, r"^[0-9a-f]{64}$")
        self.assertEqual(server_fingerprint, client_fingerprint)
        for endpoint in (server, client):
            endpoint.wait_for("ML-KEM handshake awal selesai")
            endpoint.wait_for("Ketik pesan lalu Enter.")

        for sender, receiver, message in (
            (client, server, "U-01"),
            (server, client, "D-01"),
            (client, server, "U-02 é"),
            (server, client, "D-02"),
        ):
            sender.send(message)
            sender.wait_for("[Terkirim]")
            self.assertEqual(receiver.wait_for("[Pesan diterima]:").strip(), f"[Pesan diterima]: {message}")

        client.send("/quit")
        self.assertEqual(client.process.wait(timeout=TIMEOUT), 0)
        server.wait_for("Peer menutup koneksi.")
        server.process.stdin.close()
        self.assertEqual(server.process.wait(timeout=TIMEOUT), 0)

    def original_chat(self):
        configured_path = os.environ.get("HPQC_BASELINE_ZIP")
        archive_path = Path(configured_path) if configured_path else DEFAULT_BASELINE
        if not configured_path and not archive_path.is_file():
            self.skipTest("Set HPQC_BASELINE_ZIP to the Stage 00 archive to test the original CLI")
        with ZipFile(archive_path) as archive:
            source = archive.read("chat.py")
        self.assertEqual(sha256(source).hexdigest(), BASELINE_CHAT_SHA256)
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        script = Path(temporary.name) / "chat.py"
        script.write_bytes(source)
        return script

    def test_refactored_entry_points_exchange_messages(self):
        self.exchange(("server.py",), ("client.py",))

    def test_original_client_with_refactored_server(self):
        self.exchange(("chat.py", "server"), (self.original_chat(), "client"))

    def test_refactored_client_with_original_server(self):
        self.exchange((self.original_chat(), "server"), ("chat.py", "client"))
