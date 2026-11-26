"""Connection defaults and framing limit inherited from the prototype."""

from argparse import ArgumentParser

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5050
CONNECT_TIMEOUT = 10
MAX_FRAME = 1024 * 1024


def add_endpoint_arguments(parser: ArgumentParser) -> None:
    """Register the shared host and port options."""
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
