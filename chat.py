#!/usr/bin/env python3
"""Compatibility entry point for the original two-way chat command."""

import argparse

import client
import server
from config import MAX_FRAME, add_endpoint_arguments
from crypto_engine.kdf import keys_from_secret
from protocol.session import handle
from protocol.transport import recv_exact, recv_frame, send_frame

__all__ = ["MAX_FRAME", "recv_exact", "recv_frame", "send_frame", "keys_from_secret", "handle", "main"]


def main() -> None:
    parser = argparse.ArgumentParser(description="HPQC demo dua arah")
    parser.add_argument("mode", choices=("server", "client"))
    add_endpoint_arguments(parser)
    args = parser.parse_args()
    run = server.run if args.mode == "server" else client.run
    run(args.host, args.port)


if __name__ == "__main__":
    main()
