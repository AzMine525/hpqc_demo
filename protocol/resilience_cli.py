"""Stage 09 authenticated inbox and reconnecting sender for a provisioned lab pair."""

from contextlib import closing
import json
import math
from pathlib import Path
import socket
import sqlite3

from protocol.data_v2 import MAX_DATA, RecordError
from protocol.handshake_cli import endpoint_parser
from protocol.handshake_v2 import HandshakeError
from protocol.resilience import Inbox, Policy, RecoveryClient, serve_session


def emit(row: dict) -> None:
    """Write one event containing public identifiers and measurements."""
    print(json.dumps(row), flush=True)


def main() -> None:
    parser = endpoint_parser(__doc__)
    parser.add_argument("--inbox", type=Path, help="Server database dedicated to this peer")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--text")
    inputs.add_argument("--input", type=Path)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--message-id", help="Resume one logical send using its 32 hex digits")
    parser.add_argument("--interval", type=float, default=2.0, help="Idle seconds between messages")
    parser.add_argument("--heartbeat", type=float, default=1.0, help="Client idle probe interval")
    parser.add_argument("--idle-timeout", type=float, default=15.0, help="Server idle deadline")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--backoff", type=float, default=0.2)
    parser.add_argument("--backoff-cap", type=float, default=2.0)
    args = parser.parse_args()
    try:
        policy = Policy(args.timeout, args.retries, args.backoff, args.backoff_cap)
        if (args.count < 1 or not math.isfinite(args.interval) or args.interval < 0 or
                not all(math.isfinite(v) and v > 0 for v in (args.heartbeat, args.idle_timeout))):
            parser.error("Invalid timing or count")
        with args.psk_file.open("rb") as src:
            psk = src.read(33)
        if len(psk) != 32:
            parser.error("PSK must be exactly 32 raw bytes")
        address = (args.host, args.port)
        if args.role == "server":
            if not args.inbox or args.text is not None or args.input is not None or args.message_id is not None:
                parser.error("Server requires --inbox and no outgoing payload")
            with closing(Inbox(args.inbox)) as inbox, socket.socket() as listener:
                listener.bind(address)
                listener.listen(1)
                emit(dict(event="listening", port=listener.getsockname()[1]))
                while True:
                    sock, _ = listener.accept()
                    with sock:
                        try:
                            serve_session(sock, psk, args.suite, inbox, args.timeout, args.idle_timeout, emit)
                        except (HandshakeError, RecordError, EOFError, OSError, RuntimeError) as exc:
                            emit(dict(event="session_closed", error=type(exc).__name__))
        else:
            if args.inbox or (args.text is None and args.input is None):
                parser.error("Client requires --text or --input")
            logical_id = None
            if args.message_id is not None:
                if args.count != 1 or len(args.message_id) != 32:
                    parser.error("--message-id requires 32 hex digits and --count 1")
                logical_id = bytes.fromhex(args.message_id)
            if args.input is None:
                payload = args.text.encode("utf-8")
            else:
                with args.input.open("rb") as src:
                    payload = src.read(MAX_DATA + 1)
            with closing(RecoveryClient(address, psk, suite=args.suite, policy=policy, event=emit)) as client:
                for index in range(args.count):
                    if index:
                        client.wait(args.interval, args.heartbeat)
                    client.send(payload, logical_id)
    except KeyboardInterrupt:
        return
    except (HandshakeError, EOFError, OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        parser.exit(1, f"Recovery endpoint stopped ({type(exc).__name__}).\n")


if __name__ == "__main__":
    main()
