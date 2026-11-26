"""Passive Windows IPv4 loopback capture for the two sockets owned by the experiment."""

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import socket
import struct
import time
from threading import Event


def segment(packet, ports):
    if len(packet) < 40 or packet[0] >> 4 != 4 or packet[9] != 6:
        return None
    if packet[12:20] != socket.inet_aton("127.0.0.1") * 2:
        return None
    ip_len = (packet[0] & 15) * 4
    if ip_len < 20 or len(packet) < ip_len + 20:
        return None
    src, dst, seq = struct.unpack_from("!HHI", packet, ip_len)
    if (src, dst) not in (ports, ports[::-1]):
        return None
    start = ip_len + (packet[ip_len+12] >> 4) * 4
    end = int.from_bytes(packet[2:4], "big")
    if not ip_len + 20 <= start <= end <= len(packet):
        raise ValueError("Incomplete captured TCP/IP header or packet")
    return src, seq, packet[ip_len+13], packet[start:end]


def reassemble(parts):
    """Order by sequence relative to the SYN and tolerate consistent retransmissions."""
    origins = {(seq + 1) % 2**32 for seq, flags, _ in parts if flags & 2}
    if len(origins) != 1:
        raise ValueError("Missing or ambiguous TCP SYN")
    origin, = origins
    data = bytearray()
    blocks = sorted(((seq + bool(flags & 2) - origin) % 2**32, block)
                    for seq, flags, block in parts if block)
    for offset, block in blocks:
        overlap = min(len(data) - offset, len(block))
        if overlap < 0 or data[offset:offset+overlap] != block[:overlap]:
            raise ValueError("Gap or conflicting bytes in TCP capture")
        data.extend(block[overlap:])
    return bytes(data)


class PacketCapture:
    def __init__(self, ports, path):
        self.ports = ports
        self.path = path
        self.stop = Event()

    def __enter__(self):
        self.raw = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_IP)
        try:
            self.raw.bind(("127.0.0.1", 0))
            self.raw.ioctl(socket.SIO_RCVALL, 3)  # RCVALL_IPLEVEL, non-promiscuous.
            self.raw.settimeout(0.2)
            self.pool = ThreadPoolExecutor(1)
            self.worker = self.pool.submit(self._record)
        except BaseException:
            self.raw.close()
            raise
        return self

    def _record(self):
        with self.path.open("xb") as out:
            # Classic pcap, little endian, microsecond timestamps, LINKTYPE_RAW.
            out.write(struct.pack("<IHHIIII", 0xa1b2c3d4, 2, 4, 0, 0, 65535, 101))
            while True:
                try:
                    packet = self.raw.recv(65535)
                except socket.timeout:
                    if self.stop.is_set():
                        return
                    continue
                if segment(packet, self.ports) is not None:
                    sec, usec = divmod(time.time_ns() // 1000, 1_000_000)
                    out.write(struct.pack("<IIII", sec, usec, len(packet), len(packet)) + packet)
                elif self.stop.is_set():
                    # Other loopback activity must not keep the capture alive indefinitely.
                    return

    def __exit__(self, exc_type, exc, tb):
        self.stop.set()
        try:
            self.worker.result(timeout=5)
        finally:
            self.raw.close()
            self.pool.shutdown()

    def verify(self, client_frames, server_frames):
        """Reopen the saved pcap, reconstruct both streams and compare every byte."""
        parts = {p: [] for p in self.ports}
        blob = self.path.read_bytes()
        pos = 24
        while pos < len(blob):
            _, _, captured, original = struct.unpack_from("<IIII", blob, pos)
            pos += 16
            if captured != original or pos + captured > len(blob):
                raise ValueError("Truncated pcap record")
            src, seq, flags, payload = segment(blob[pos:pos+captured], self.ports)
            parts[src].append((seq, flags, payload))
            pos += captured
        for port, frames in zip(self.ports, (client_frames, server_frames)):
            if reassemble(parts[port]) != b"".join(frames):
                raise ValueError("Captured stream differs from endpoint bytes")
        return dict(file=self.path.name, sha256=sha256(blob).hexdigest(),
                    packets=sum(map(len, parts.values())), reassembly="PASS")
