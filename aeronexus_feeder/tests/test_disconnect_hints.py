"""Remote-close diagnostics and real official-relay logging, using local sockets only."""
import logging
from pathlib import Path
import select
import socket
import sys
import threading
import unittest
from unittest.mock import Mock

APP = Path(__file__).resolve().parents[1]
LIB = APP / "rootfs/usr/local/lib/aeronexus"
sys.path.insert(0, str(LIB))
import engine_runner as runner
import manager
import relay
import upstream
from test_relay import UUID, exact, listener

ORIGINAL = (APP / "upstream/feed_relay.original.py.txt").read_bytes()


class DisconnectHintTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.messages = []
        self.hints = runner.DisconnectHints(self.messages.append, lambda: self.now)

    def observed(self):
        sock = Mock()
        sock.recv.return_value = b""
        return runner.ObservedFeedSocket(sock, self.hints)

    def test_immediate_remote_eof_warns_once_without_uuid_value(self):
        sock = self.observed()
        self.now = 1.0
        self.assertEqual(sock.recv(4096), b"")
        sock.recv(4096)
        self.assertEqual(len(self.messages), 1)
        self.assertIn("UUID가 다른 곳에서 사용 중일 수 있습니다", self.messages[0])
        self.assertNotIn(UUID, self.messages[0])
        self.assertNotIn(UUID[:8], self.messages[0])

    def test_ten_second_boundary_and_established_session_close(self):
        for age, expected in [(10.0, 1), (10.001, 0), (300.0, 0)]:
            with self.subTest(age=age):
                self.setUp()
                sock = self.observed()
                self.now = age
                sock.recv(4096)
                self.assertEqual(len(self.messages), expected)

    def test_remote_reset_on_read_is_reported_and_reraised(self):
        for error in (ConnectionResetError, ConnectionAbortedError):
            with self.subTest(error=error):
                self.setUp()
                sock = self.observed()
                sock.sock.recv.side_effect = error("remote closed")
                with self.assertRaises(error):
                    sock.recv(4096)
                self.assertEqual(len(self.messages), 1)

    def test_broken_pipe_or_reset_during_uuid_send_is_reported_and_reraised(self):
        for error in (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            with self.subTest(error=error):
                self.setUp()
                sock = self.observed()
                sock.sock.sendall.side_effect = error("remote closed")
                with self.assertRaises(error):
                    sock.sendall(b"\x1a\xe4" + UUID.encode())
                self.assertEqual(len(self.messages), 1)

    def test_timeout_does_not_suggest_uuid_conflict(self):
        for method, argument in [("recv", 4096), ("sendall", b"data")]:
            with self.subTest(method=method):
                sock = self.observed()
                getattr(sock.sock, method).side_effect = TimeoutError("timed out")
                with self.assertRaises(TimeoutError):
                    getattr(sock, method)(argument)
        self.assertEqual(self.messages, [])

    def test_local_shutdown_does_not_warn(self):
        sock = self.observed()
        sock.close()
        sock.recv(4096)
        self.assertEqual(self.messages, [])
        sock.sock.close.assert_called_once_with()

    def test_reconnect_warnings_are_limited_to_one_per_minute(self):
        self.observed().recv(4096)
        self.now = 5.0
        self.observed().recv(4096)
        self.assertEqual(len(self.messages), 1)
        self.now = 60.0
        self.observed().recv(4096)
        self.assertEqual(len(self.messages), 2)

    def test_only_destination_socket_is_observed_and_connect_failure_is_not(self):
        raw = Mock()
        connect = Mock(return_value=raw)
        bounded = runner.runtime_connect(connect, "server", 30004, self.hints)
        self.assertIs(bounded("receiver", 30005, 5.0), raw)
        raw.settimeout.assert_called_with(5.0)
        self.assertIsInstance(bounded("server", 30004, 10.0), runner.ObservedFeedSocket)
        connect.assert_called_with("server", 30004, 10.0)
        connect.side_effect = ConnectionRefusedError("not connected")
        with self.assertRaises(ConnectionRefusedError):
            bounded("server", 30004, 10.0)
        self.assertEqual(self.messages, [])

    def test_socket_bytes_and_select_identity_are_preserved(self):
        raw, peer = socket.socketpair()
        peer.settimeout(2)
        sock = runner.ObservedFeedSocket(raw, self.hints)
        try:
            uuid_frame = b"\x1a\xe4" + UUID.encode()
            sock.sendall(uuid_frame)
            self.assertEqual(exact(peer, len(uuid_frame)), uuid_frame)
            peer.sendall(b"unaltered bytes")
            ready, _, _ = select.select([sock], [], [], 2)
            self.assertEqual(ready, [sock])
            self.assertEqual(sock.recv(4096), b"unaltered bytes")
        finally:
            sock.close()
            peer.close()
        self.assertEqual(self.messages, [])

    def test_diagnostic_failure_does_not_change_eof(self):
        self.hints.log = Mock(side_effect=OSError("log unavailable"))
        self.assertEqual(self.observed().recv(4096), b"")


class OfficialDisconnectLoggingTests(unittest.TestCase):
    def capture_disconnect(self, close_server):
        source, destination = listener(), listener()
        settings = relay.Settings(UUID, "127.0.0.1", source.getsockname()[1])
        candidate = upstream.identify(ORIGINAL, "127.0.0.1", destination.getsockname()[1])
        worker = manager.Worker(settings)
        observed = threading.Event()
        expected = "UUID가 다른 곳에서 사용 중일 수 있습니다" if close_server else "수신기 연결 끊김"

        class Marker(logging.Handler):
            def emit(self, record):
                if expected in record.getMessage():
                    observed.set()

        handler = Marker()
        sockets = []
        try:
            with self.assertLogs("aeronexus", level="INFO") as logs:
                manager.LOG.addHandler(handler)
                try:
                    worker.start(candidate, settings.beast_host, settings.beast_port)
                    up, _ = destination.accept()
                    sockets.append(up)
                    up.settimeout(5)
                    self.assertEqual(exact(up, 38), b"\x1a\xe4" + UUID.encode())
                    src, _ = source.accept()
                    sockets.append(src)
                    remote = up if close_server else src
                    remote.shutdown(socket.SHUT_RDWR)
                    remote.close()
                    self.assertTrue(observed.wait(5), "Expected disconnect diagnostic was not logged")
                    self.assertTrue(worker.alive(), "Official reconnect loop must remain active")
                finally:
                    worker.stop()
                    manager.LOG.removeHandler(handler)
            return logs.output
        finally:
            worker.stop()
            manager.LOG.removeHandler(handler)
            for sock in sockets:
                sock.close()
            source.close()
            destination.close()

    def test_actual_official_relay_promotes_early_server_close_to_warning(self):
        logs = self.capture_disconnect(close_server=True)
        rendered = "\n".join(logs)
        self.assertTrue(any(line.startswith("WARNING:") and "UUID가 다른 곳에서 사용 중일 수 있습니다" in line
                            for line in logs))
        self.assertNotIn(UUID, rendered)
        self.assertNotIn(UUID[:8], rendered)

    def test_actual_beast_source_close_does_not_suggest_duplicate_uuid(self):
        rendered = "\n".join(self.capture_disconnect(close_server=False))
        self.assertNotIn("UUID가 다른 곳에서 사용 중일 수 있습니다", rendered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
