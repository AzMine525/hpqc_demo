"""Listen for a single chat client."""

import argparse
import socket

from config import add_endpoint_arguments
from protocol.session import handle


def run(host: str, port: int) -> None:
    """Bind to the requested endpoint and accept one chat session."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((host, port))
        listener.listen(1)
        print(f"Menunggu koneksi pada {host}:{port}...")
        conn, addr = listener.accept()
        print("Client terhubung dari:", addr)
        with conn:
            handle(conn, server=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="HPQC demo dua arah (server)")
    add_endpoint_arguments(parser)
    args = parser.parse_args()
    run(args.host, args.port)


if __name__ == "__main__":
    main()
