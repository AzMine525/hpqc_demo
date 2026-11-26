"""Connect as the chat client."""

import argparse
import socket

from config import CONNECT_TIMEOUT, add_endpoint_arguments
from protocol.session import handle


def run(host: str, port: int) -> None:
    """Connect to the server and run one chat session."""
    with socket.create_connection((host, port), timeout=CONNECT_TIMEOUT) as sock:
        sock.settimeout(None)
        handle(sock, server=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="HPQC demo dua arah (client)")
    add_endpoint_arguments(parser)
    args = parser.parse_args()
    run(args.host, args.port)


if __name__ == "__main__":
    main()
