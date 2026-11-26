"""Run one Stage 04 handshake, report the public session ID, then close."""

import argparse
import math
from pathlib import Path
import socket

from config import CONNECT_TIMEOUT, DEFAULT_PORT
from crypto_engine.v2.suites import DEFAULT_SUITE, SUITES
from protocol.handshake_v2 import DEFAULT_TIMEOUT, HandshakeError, establish


def endpoint_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("role", choices=("client", "server"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--psk-file", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--suite", choices=tuple(SUITES), default=DEFAULT_SUITE,
                        help="Local suite required of the peer (default: %(default)s)")
    return parser


def endpoint(args: argparse.Namespace, parser: argparse.ArgumentParser) -> tuple[socket.socket, bytes]:
    """Read the local PSK and open a single TCP connection for either v2 CLI."""
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be finite and positive")
    with args.psk_file.open("rb") as source:
        psk = source.read(33)
    if len(psk) != 32:
        parser.error("PSK file must contain exactly 32 raw bytes")
    if args.role == "server":
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind((args.host, args.port))
            listener.listen(1)
            print(f"Menunggu koneksi handshake pada {args.host}:{listener.getsockname()[1]}", flush=True)
            sock, _ = listener.accept()
    else:
        sock = socket.create_connection((args.host, args.port), timeout=CONNECT_TIMEOUT)
    return sock, psk


def main() -> None:
    parser = endpoint_parser(__doc__)
    args = parser.parse_args()
    try:
        sock, psk = endpoint(args, parser)
        with establish(sock, role=args.role, psk=psk, timeout=args.timeout, suite=args.suite) as session:
            print(f"Handshake terkonfirmasi. Session ID {session.session_id.hex()}")
    except (HandshakeError, OSError, ValueError) as exc:
        parser.exit(1, f"Handshake gagal ({type(exc).__name__}).\n")


if __name__ == "__main__":
    main()
