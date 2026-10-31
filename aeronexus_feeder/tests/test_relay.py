"""Offline protocol and TCP regression tests. No AeroNexus credentials required."""
import contextlib
import json
import os
from pathlib import Path
import random
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1]
LIB = APP / "rootfs/usr/local/lib/aeronexus"
sys.path.insert(0, str(LIB))
import beast
import relay

UUID = "12345678-1234-4321-8765-123456789abc"


def frame(df=17, typ=0x33, timestamp=b"\x01\x02\x03\x04\x05\x06", escaped=False):
    size = beast.PLEN[typ]
    data = bytes([df << 3]) + bytes(range(1, size))
    if escaped:
        data = data[:-1] + b"\x1a"
    body = timestamp + b"\x1a" + data
    return b"\x1a" + bytes([typ]) + body.replace(b"\x1a", b"\x1a\x1a")


class ParserTests(unittest.TestCase):
    def test_uuid_is_exact_wire_format(self):
        self.assertEqual(beast.uuid_frame(UUID), b"\x1a\xe4" + UUID.encode("ascii"))
        self.assertEqual(len(beast.uuid_frame(UUID)), 38)

    def test_df17_df18_only(self):
        sp = beast.Splitter("adsb")
        a, b, c = frame(17), frame(18), frame(11)
        self.assertEqual(sp.feed(a + b + c + frame(4, 0x32) + beast.HB), a + b)
        self.assertEqual((sp.n_in, sp.n_out), (5, 2))

    def test_all_mode_still_excludes_mlat(self):
        a = frame(17, timestamp=beast.MLAT_TS)
        b = frame(18)
        sp = beast.Splitter("all")
        self.assertEqual(sp.feed(a + beast.HB + b), beast.HB + b)
        self.assertEqual(sp.n_mlat, 1)

    def test_every_split_boundary_and_escaped_payload(self):
        expected = frame(17, escaped=True) + frame(18, timestamp=b"\x1a" * 6)
        for split in range(len(expected) + 1):
            sp = beast.Splitter("adsb")
            self.assertEqual(sp.feed(expected[:split]) + sp.feed(expected[split:]), expected)

    def test_random_chunks_and_bytewise(self):
        data = b"noise" + frame(17) + beast.uuid_frame(UUID) + frame(18, escaped=True) + frame(11)
        expected = frame(17) + frame(18, escaped=True)
        for seed in range(30):
            rng = random.Random(seed)
            sp, out, offset = beast.Splitter("adsb"), b"", 0
            while offset < len(data):
                count = 1 if seed == 0 else rng.randint(1, 15)
                out += sp.feed(data[offset:offset + count])
                offset += count
            self.assertEqual(out, expected)

    def test_drops_foreign_uuid_and_receiver_id(self):
        receiver = b"\x1a\xe3" + b"12\x1a\x1a34567"
        sp = beast.Splitter("all")
        self.assertEqual(sp.feed(beast.uuid_frame(UUID) + receiver + frame()), frame())

    def test_recovers_from_truncated_receiver_id(self):
        sp = beast.Splitter("adsb")
        self.assertEqual(sp.feed(b"\x1a\xe3abc" + frame()), frame())

    def test_recovers_from_truncated_adsb_and_unknown_type(self):
        sp = beast.Splitter("adsb")
        self.assertEqual(sp.feed(b"garbage\x1a\xff\x1a\x33abc" + frame()), frame())
        self.assertGreater(sp.n_resync, 0)

    def test_garbage_does_not_grow_memory(self):
        sp = beast.Splitter("adsb")
        for _ in range(100):
            sp.feed(b"z" * 10000)
        self.assertLessEqual(len(sp.buf), beast.BUF_MAX)


class SettingsTests(unittest.TestCase):
    def load(self, data):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "options.json"
            p.write_text(json.dumps(data), encoding="utf-8")
            return relay.Settings.load(p)

    def test_uuid_only_defaults(self):
        s = self.load({"uuid": UUID.upper()})
        self.assertEqual(s.uuid, UUID)
        self.assertEqual((s.beast_host, s.beast_port, s.filter, s.stats_interval), ("", 30005, "adsb", 60))

    def test_empty_uuid_allowed(self):
        self.assertEqual(self.load({"uuid": ""}).uuid, "")

    def test_invalid_uuid_is_rejected_without_value_in_error(self):
        for value in [None, 1, "private-secret", UUID + "\n", " " + UUID, UUID.replace("-", "")]:
            with self.subTest(value=value), self.assertRaises(relay.ConfigError) as caught:
                self.load({"uuid": value})
            self.assertNotIn("private-secret", str(caught.exception))

    def test_invalid_options(self):
        for value in [{"beast_port": 0}, {"beast_port": True}, {"beast_port": "30005"},
                      {"filter": "bad"}, {"stats_interval": 1}, {"feed_host": "evil.example"},
                      {"beast_host": "http://host"}, {"beast_host": "host:30005"},
                      {"beast_host": "host\nINJECT"}, []]:
            with self.subTest(value=value), self.assertRaises(relay.ConfigError):
                self.load(value)

    def test_invalid_json_and_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "options.json"
            with self.assertRaises(relay.ConfigError):
                relay.Settings.load(p)
            p.write_text("{", encoding="utf-8")
            with self.assertRaises(relay.ConfigError):
                relay.Settings.load(p)

    def test_empty_uuid_process_stays_idle(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "options.json"
            p.write_text('{"uuid":""}', encoding="utf-8")
            proc = subprocess.Popen([sys.executable, "-B", str(LIB / "manager.py"), "--options", str(p)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            first_line = []
            ready = threading.Event()
            def read_startup():
                first_line.append(proc.stderr.readline())
                ready.set()
            reader = threading.Thread(target=read_startup, daemon=True)
            reader.start()
            try:
                self.assertTrue(ready.wait(5), "Startup log did not arrive")
                self.assertIsNone(proc.poll())
            finally:
                proc.terminate()
                reader.join(timeout=2)
                out, err = proc.communicate(timeout=5)
            err = b"".join(first_line) + err
            self.assertIn(b"Waiting without network connections", err)
            self.assertNotIn(b"connected", out + err)


class DiscoveryTests(unittest.TestCase):
    def test_standard_and_local_slugs(self):
        for slug in ["f1c878cb_adsb-multi-portal-feeder", "local_adsb-multi-portal-feeder"]:
            self.assertEqual(relay.choose_source({"addons": [{"slug": slug}]}), slug.replace("_", "-"))

    def test_missing_ambiguous_and_malformed_sources(self):
        for data in [{}, {"addons": []}, {"addons": [None, {}, {"slug": "evil\n_adsb-multi-portal-feeder"}]},
                     {"addons": [{"slug": "a_adsb-multi-portal-feeder"}, {"slug": "b_adsb-multi-portal-feeder"}]}]:
            with self.subTest(data=data), self.assertRaises(relay.DiscoveryError):
                relay.choose_source(data)

    def test_explicit_host_bypasses_supervisor(self):
        with patch.object(relay, "supervisor_info", side_effect=AssertionError("must not call")):
            resolver = relay.SourceResolver(relay.Settings(UUID, "receiver.example", 31005))
            self.assertEqual(resolver.resolve(), ("receiver.example", 31005))

    def test_discovery_cache_and_refresh(self):
        with patch.object(relay, "supervisor_info", return_value={"addons": [{"slug": "local_adsb-multi-portal-feeder"}]}) as get:
            resolver = relay.SourceResolver(relay.Settings(UUID))
            resolver.resolve()
            resolver.resolve()
            self.assertEqual(get.call_count, 1)
            resolver.expires = 0
            resolver.resolve()
            self.assertEqual(get.call_count, 2)

    def test_read_only_default_role_endpoint_and_token_not_logged(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return b'{"result":"ok","data":{"addons":[]}}'
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-private-token"}), patch.object(relay, "build_opener") as build:
            build.return_value.open.return_value = Response()
            self.assertEqual(relay.supervisor_info(), {"addons": []})
            req = build.return_value.open.call_args.args[0]
            self.assertEqual(req.full_url, "http://supervisor/supervisor/info")
            self.assertEqual(req.get_method(), "GET")
            self.assertEqual(req.get_header("Authorization"), "Bearer test-private-token")

    def test_redirect_refused(self):
        with self.assertRaises(relay.DiscoveryError):
            relay.NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.example")


def listener():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    sock.settimeout(5)
    return sock


def exact(sock, size):
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            break
        data += chunk
    return data


class NetworkTests(unittest.TestCase):
    def exercise(self, reconnect=False, uuid=UUID):
        source, upstream = listener(), listener()
        settings = relay.Settings(uuid, "127.0.0.1", source.getsockname()[1])
        app = relay.Relay(settings, feed_host="127.0.0.1", feed_port=upstream.getsockname()[1])
        app.src_retry.delay = app.up_retry.delay = .05
        stop = threading.Event()
        errors = []
        def run():
            try:
                app.run(stop.is_set)
            except BaseException as exc:
                errors.append(exc)
        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        sockets = []
        try:
            src, _ = source.accept()
            up, _ = upstream.accept()
            sockets += [src, up]
            up.settimeout(5)
            self.assertEqual(exact(up, 38), beast.uuid_frame(uuid))
            src.sendall(frame(11) + frame(17, timestamp=beast.MLAT_TS) + frame(17, escaped=True) + frame(18))
            expected = frame(17, escaped=True) + frame(18)
            self.assertEqual(exact(up, len(expected)), expected)
            if reconnect:
                up.shutdown(socket.SHUT_RDWR)
                up.close()
                up2, _ = upstream.accept()
                sockets.append(up2)
                up2.settimeout(5)
                self.assertEqual(exact(up2, 38), beast.uuid_frame(uuid))
                # Source reconnection must discard the previous partial frame.
                src.sendall(frame()[:8])
                time.sleep(.05)
                src.shutdown(socket.SHUT_RDWR)
                src.close()
                src2, _ = source.accept()
                sockets.append(src2)
                src2.sendall(frame(18))
                self.assertEqual(exact(up2, len(frame(18))), frame(18))
            else:
                with patch.object(relay, "HEARTBEAT_S", .05):
                    self.assertEqual(exact(up, len(beast.HB)), beast.HB)
        finally:
            stop.set()
            for sock in sockets:
                with contextlib.suppress(OSError):
                    sock.shutdown(socket.SHUT_RDWR)
                sock.close()
            worker.join(timeout=5)
            source.close()
            upstream.close()
        self.assertFalse(worker.is_alive())
        self.assertFalse(errors, errors)

    def test_real_tcp_forwarding_and_heartbeat(self):
        self.exercise()

    def test_real_tcp_source_and_upstream_reconnect_uuid_repeated(self):
        self.exercise(reconnect=True)

    def test_restarting_with_changed_uuid_sends_new_identity(self):
        self.exercise(uuid=UUID)
        self.exercise(uuid="87654321-4321-4123-8123-cba987654321")

    def test_connect_has_finite_send_timeout(self):
        source = listener()
        try:
            sock = relay.connect("127.0.0.1", source.getsockname()[1])
            other, _ = source.accept()
            self.assertEqual(sock.gettimeout(), relay.SOCKET_TIMEOUT)
            sock.close()
            other.close()
        finally:
            source.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
