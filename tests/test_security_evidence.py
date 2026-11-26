"""Stage 06 checks for rejection behavior and integrity of the evidence."""

import unittest
from unittest.mock import patch

from experiments.loopback_pcap import reassemble
from experiments.security_baseline import experiment
from protocol.data_v2 import Acknowledgement, RecordError
import test_data_v2


class SecurityEvidenceTests(unittest.TestCase):
    def channels(self):
        fixture = test_data_v2.DataTests()
        self.addCleanup(fixture.doCleanups)
        return fixture.channels()

    def test_old_data_after_three_deliveries(self):
        client, server, left, right = self.channels()
        for _ in range(3):
            mid = client.send_data(b"synthetic")
            self.assertEqual(server.receive().message_id, mid)
            self.assertEqual(client.receive(), Acknowledgement(mid))
        stale = left.frames[0]
        # Present the already consumed record to the local decoder.
        with patch.object(right, "recv", side_effect=[stale[:4], stale[4:48], stale[48:]]):
            with self.assertRaisesRegex(RecordError, "context or sequence"):
                server.receive()
        self.assertEqual(server._receive_sequence, 3)
        self.assertEqual(len(right.frames), 3)
        self.assertEqual(right.fileno(), -1)

    def test_ack_with_altered_tag_never_confirms_delivery(self):
        client, server, left, right = self.channels()
        mid = client.send_data(b"synthetic")
        server.receive()
        ack = right.frames[-1]
        changed = ack[:-1] + bytes([ack[-1] ^ 1])
        with patch.object(left, "recv", side_effect=[changed[:4], changed[4:48], changed[48:]]):
            with self.assertRaisesRegex(RecordError, "authentication failed"):
                client.receive()
        self.assertEqual(client._pending, mid)
        self.assertEqual(client._receive_sequence, 0)
        self.assertEqual(left.fileno(), -1)

    def test_same_marker_control_and_authenticated_delivery(self):
        plain = experiment(False, 0)
        secure = experiment(True, 0)
        for side, counts in (("client", [1, 0]), ("server", [0, 1])):
            self.assertEqual(plain[side]["marker_counts"], counts)
            self.assertEqual(secure[side]["marker_counts"], [0, 0])
        self.assertEqual(secure["client"]["bytes"] + secure["server"]["bytes"], 4888)

    def test_capture_reassembly_with_retransmission_and_sequence_wrap(self):
        parts = [(0xfffffffd, 2, b""), (0, 16, b"cd"), (0xfffffffe, 16, b"abc")]
        self.assertEqual(reassemble(parts + [parts[-1]]), b"abcd")

    def test_capture_gaps_and_conflicts_invalidate_evidence(self):
        for parts in ([(1, 16, b"x")], [(1, 2, b""), (3, 16, b"x")],
                      [(1, 2, b""), (2, 16, b"x"), (2, 16, b"y")]):
            with self.assertRaises(ValueError):
                reassemble(parts)
