"""Exchange one text or binary payload per endpoint over a confirmed v2 session."""

from pathlib import Path
from typing import Optional

from protocol.data_v2 import Acknowledgement, DataChannel, MAX_DATA, ReceivedData, RecordError
from protocol.handshake_cli import endpoint, endpoint_parser
from protocol.handshake_v2 import HandshakeError


def _send(channel: DataChannel, payload: bytes) -> None:
    message_id = channel.send_data(payload)
    reply = channel.receive()
    if not isinstance(reply, Acknowledgement) or reply.message_id != message_id:
        raise RecordError("Expected application ACK")
    print(f"ACK terverifikasi {message_id.hex()} ({len(payload)} byte)")


def _receive(channel: DataChannel, output: Optional[Path]) -> None:
    record = channel.receive()
    if not isinstance(record, ReceivedData):
        raise RecordError("Expected application DATA")
    if output is not None:
        with output.open("xb") as destination:
            destination.write(record.payload)
    print(f"DATA diterima {record.message_id.hex()} ({len(record.payload)} byte)")


def main() -> None:
    parser = endpoint_parser(__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="Send this UTF-8 text")
    source.add_argument("--input", type=Path, help="Send this binary file (at most 1 MiB)")
    parser.add_argument("--output", type=Path, help="Save received bytes to a new file")
    args = parser.parse_args()
    try:
        if args.input is None:
            payload = args.text.encode("utf-8")
        else:
            with args.input.open("rb") as stream:
                payload = stream.read(MAX_DATA + 1)
        if len(payload) > MAX_DATA:
            parser.error("Payload exceeds 1 MiB")
        sock, psk = endpoint(args, parser)
        with DataChannel(sock, role=args.role, psk=psk, timeout=args.timeout, suite=args.suite) as channel:
            if args.role == "client":
                _send(channel, payload)
                _receive(channel, args.output)
            else:
                _receive(channel, args.output)
                _send(channel, payload)
    except (HandshakeError, OSError, EOFError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Transfer gagal ({type(exc).__name__}).\n")


if __name__ == "__main__":
    main()
