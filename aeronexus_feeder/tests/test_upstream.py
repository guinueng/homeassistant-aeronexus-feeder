"""Offline updater, rollback, persistence, and official-engine integration tests."""
import contextlib
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

APP = Path(__file__).resolve().parents[1]
LIB = APP / "rootfs/usr/local/lib/aeronexus"
sys.path.insert(0, str(LIB))
import manager
import relay
import upstream
import refresh
from test_relay import UUID, exact, frame, listener

ORIGINAL = (APP / "upstream/feed_relay.original.py.txt").read_bytes()


def installer(code=ORIGINAL, host="aeronexus.kr", port=30004):
    return (f'#!/bin/bash\nFEED_HOST="${{AERO_FEED_HOST:-{host}}}"\n'
            f'FEED_PORT="${{AERO_FEED_PORT:-{port}}}"\n'
            'cat > "$RELAY" <<\'PYEOF\'\n').encode() + code.rstrip(b"\n") + b"\nPYEOF\n"


class Response:
    def __init__(self, data, headers=None):
        self.data, self.headers = data, headers or {}
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, size): return self.data[:size]


class UpstreamTests(unittest.TestCase):
    def test_original_extracts_and_passes_actual_subprocess_checks(self):
        candidate = upstream.extract(installer())
        self.assertEqual(candidate.code, ORIGINAL)
        self.assertEqual(candidate.sha256, hashlib.sha256(ORIGINAL).hexdigest())
        upstream.validate(candidate)

    def test_installer_shell_is_never_executed(self):
        data = installer().replace(b"#!/bin/bash\n", b"#!/bin/bash\nexit 99\nsystemctl stop everything\n")
        self.assertEqual(upstream.extract(data).code, ORIGINAL)

    def test_html_truncated_multiple_and_oversize_rejected(self):
        for source in [b"<html>Error</html>", installer()[:-20],
                       installer() + b"cat x <<'PYEOF'\n1\nPYEOF\n",
                       b"a" * (upstream.MAX_SCRIPT + 1)]:
            with self.subTest(size=len(source)), self.assertRaises(upstream.UpdateError):
                upstream.extract(source)

    def test_invalid_python_or_changed_interface_rejected(self):
        for source in [b"not python !", b"def main(): pass\n"]:
            with self.assertRaises(upstream.UpdateError):
                upstream.extract(installer(source))

    def test_bad_uuid_and_mlat_protocol_rejected(self):
        for code in [ORIGINAL.replace(b"b'\\x1a\\xe4'", b"b'\\x1a\\xe5'"),
                     ORIGINAL.replace(b"if ts == MLAT_TS:", b"if False:")]:
            self.assertNotEqual(code, ORIGINAL)
            with self.assertRaises(upstream.UpdateError):
                upstream.validate(upstream.identify(code))

    def test_broken_main_is_rejected_even_when_parser_passes(self):
        code = ORIGINAL.replace(b"def main():\n", b"def main():\n    return 0\n", 1)
        with self.assertRaises(upstream.UpdateError):
            upstream.validate(upstream.identify(code))

    def test_redirect_only_allows_same_https_origin(self):
        handler = upstream.OfficialOriginOnly()
        for target in ["http://aeronexus.kr/feed.sh", "https://evil.example/feed.sh", "https://aeronexus.kr:444/feed.sh"]:
            with self.assertRaises(upstream.UpdateError):
                handler.redirect_request(None, None, 302, "", {}, target)

    def test_child_does_not_inherit_supervisor_token_or_other_secrets(self):
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "private", "GITHUB_TOKEN": "private"}):
            env = upstream.child_environment(UUID, "receiver", 30005, "adsb", upstream.identify(ORIGINAL))
        self.assertNotIn("SUPERVISOR_TOKEN", env)
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertEqual(env["UUID"], UUID)

    def test_endpoint_changes_have_a_distinct_release(self):
        a = upstream.extract(installer(port=30004))
        b = upstream.extract(installer(port=30006))
        self.assertEqual(a.sha256, b.sha256)
        self.assertNotEqual(a.release_id, b.release_id)

    def test_cache_survives_restart_and_corruption_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            store = upstream.VersionStore(Path(directory))
            first = store.working()
            second = upstream.identify(ORIGINAL + b"\n# new official version\n")
            upstream.validate(second)
            store.activate(second)
            restored = upstream.VersionStore(Path(directory))
            self.assertEqual(restored.working().release_id, second.release_id)
            (Path(directory) / (second.release_id + ".py")).write_bytes(b"corrupt")
            self.assertEqual(upstream.VersionStore(Path(directory)).working().release_id, first.release_id)

    def test_cache_digest_prevents_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(upstream.VersionStore(Path(directory)).load("../../secrets"))

    def test_download_change_then_304_keeps_pending_update_available(self):
        with tempfile.TemporaryDirectory() as directory:
            store = upstream.VersionStore(Path(directory))
            store.working()
            newer = ORIGINAL + b"\n# changed\n"
            with patch.object(upstream, "build_opener") as build:
                build.return_value.open.return_value = Response(installer(newer), {"Last-Modified": "new-date"})
                candidate = store.check()
                self.assertEqual(candidate.code, newer)
                build.return_value.open.side_effect = HTTPError(upstream.SOURCE_URL, 304, "", {}, None)
                recovered = store.check()
                self.assertEqual(recovered.release_id, candidate.release_id)
                request = build.return_value.open.call_args.args[0]
                self.assertEqual(request.get_header("If-modified-since"), "new-date")

    def test_download_failure_keeps_active_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            store = upstream.VersionStore(Path(directory))
            original = store.working()
            with patch.object(upstream, "build_opener") as build:
                build.return_value.open.side_effect = URLError("offline")
                with self.assertRaises(upstream.UpdateError):
                    store.check()
            self.assertEqual(store.working().release_id, original.release_id)

    def test_update_interval_options(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text(json.dumps({"uuid": UUID, "update_interval": 300}))
            self.assertEqual(relay.Settings.load(path).update_interval, 300)
            path.write_text(json.dumps({"uuid": UUID, "update_interval": 10}))
            with self.assertRaises(relay.ConfigError): relay.Settings.load(path)

    def test_refresh_option_requires_a_boolean(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text(json.dumps({"uuid": UUID, "refresh_upstream": True}))
            self.assertTrue(relay.Settings.load(path).refresh_upstream)
            path.write_text(json.dumps({"uuid": UUID, "refresh_upstream": "true"}))
            with self.assertRaises(relay.ConfigError): relay.Settings.load(path)


class FakeWorker:
    def __init__(self): self.running, self.started = False, []
    def start(self, candidate, host, port):
        self.started.append(candidate.release_id)
        self.running = True
    def stop(self): self.running = False
    def alive(self): return self.running


class Resolver:
    def resolve(self): return ("receiver", 30005)


class ManagerTests(unittest.TestCase):
    def setup_manager(self, directory):
        store = upstream.VersionStore(Path(directory))
        worker = FakeWorker()
        app = manager.Manager(relay.Settings(UUID), store, Resolver(), worker)
        return app, worker, store

    def test_checked_update_starts_then_commits_after_probation(self):
        with tempfile.TemporaryDirectory() as directory:
            app, worker, store = self.setup_manager(directory)
            newer = upstream.identify(ORIGINAL + b"\n# new\n")
            previous = app.active.release_id
            with patch.object(store, "check", return_value=newer):
                app.tick(time.monotonic())
            self.assertEqual(worker.started[-1], newer.release_id)
            self.assertEqual(store.state["active"], previous)
            app.tick(app.probation_until + 1)
            self.assertEqual(store.state["active"], newer.release_id)
            self.assertEqual(store.state["previous"], previous)

    def test_new_worker_crash_rolls_back_and_is_not_committed(self):
        with tempfile.TemporaryDirectory() as directory:
            app, worker, store = self.setup_manager(directory)
            newer = upstream.identify(ORIGINAL + b"\n# crash\n")
            previous = app.active.release_id
            with patch.object(store, "check", return_value=newer):
                app.tick(time.monotonic())
            worker.running = False
            app.tick(time.monotonic())
            self.assertEqual(worker.started[-1], previous)
            self.assertEqual(store.state["active"], previous)
            self.assertEqual(store.state["rejected"], newer.release_id)

    def test_offline_check_still_starts_existing_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            app, worker, store = self.setup_manager(directory)
            with patch.object(store, "check", side_effect=upstream.UpdateError("offline")):
                app.tick(time.monotonic())
            self.assertTrue(worker.alive())

    def test_no_second_check_after_hours_of_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            app, worker, store = self.setup_manager(directory)
            now = time.monotonic()
            with patch.object(store, "check", return_value=app.active) as check:
                app.tick(now)
                app.tick(now + 3601)
                app.tick(now + 86401)
            self.assertEqual(check.call_count, 1)

    def test_normal_restart_uses_cache_without_http_check(self):
        with tempfile.TemporaryDirectory() as directory:
            app, _, store = self.setup_manager(directory)
            with patch.object(store, "check", return_value=app.active):
                app.tick(time.monotonic())
            restored = upstream.VersionStore(Path(directory))
            restarted = manager.Manager(relay.Settings(UUID), restored, Resolver(), FakeWorker())
            with patch.object(restored, "check", side_effect=AssertionError("must not poll")):
                restarted.tick(time.monotonic())
            self.assertFalse(restarted.check_pending)

    def test_new_app_version_checks_once_again(self):
        with tempfile.TemporaryDirectory() as directory:
            app, _, store = self.setup_manager(directory)
            with patch.object(store, "check", return_value=app.active):
                app.tick(time.monotonic())
            upgraded = manager.Manager(relay.Settings(UUID), store, Resolver(), FakeWorker(), app_version="future")
            with patch.object(store, "check", return_value=upgraded.active) as check:
                upgraded.tick(time.monotonic())
                upgraded.tick(time.monotonic() + 3601)
            self.assertEqual(check.call_count, 1)
            self.assertEqual(store.state["checked_app_version"], "future")

    def test_failed_initial_check_only_retries_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            app, _, store = self.setup_manager(directory)
            with patch.object(store, "check", side_effect=upstream.UpdateError("offline")) as check:
                app.tick(time.monotonic())
                app.tick(time.monotonic() + 86401)
            self.assertEqual(check.call_count, 1)
            restarted = manager.Manager(relay.Settings(UUID), store, Resolver(), FakeWorker())
            self.assertTrue(restarted.check_pending)

    def test_restart_during_probation_resumes_cached_candidate_without_http(self):
        with tempfile.TemporaryDirectory() as directory:
            app, _, store = self.setup_manager(directory)
            newer = upstream.identify(ORIGINAL + b"\n# downloaded candidate\n")
            with patch.object(store, "check", return_value=newer):
                app.tick(time.monotonic())
            restored = upstream.VersionStore(Path(directory))
            worker = FakeWorker()
            restarted = manager.Manager(relay.Settings(UUID), restored, Resolver(), worker)
            with patch.object(restored, "check", side_effect=AssertionError("must not poll")):
                restarted.tick(time.monotonic())
            self.assertEqual(worker.started[-1], newer.release_id)

    def test_manual_refresh_checks_even_when_app_version_is_already_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            app, _, store = self.setup_manager(directory)
            with patch.object(store, "check", return_value=app.active):
                app.tick(time.monotonic())
            requested = manager.Manager(replace(relay.Settings(UUID), refresh_upstream=True), store, Resolver(), FakeWorker())
            with patch.object(store, "check", return_value=requested.active) as check, patch.object(manager, "clear_refresh_request", return_value=True) as acknowledge:
                requested.tick(time.monotonic())
                requested.tick(time.monotonic() + 86401)
            self.assertEqual(check.call_count, 1)
            acknowledge.assert_called_once_with()

    def test_failed_manual_check_leaves_request_for_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            app, _, store = self.setup_manager(directory)
            requested = manager.Manager(replace(relay.Settings(UUID), refresh_upstream=True), store, Resolver(), FakeWorker())
            with patch.object(store, "check", side_effect=upstream.UpdateError("offline")), patch.object(manager, "clear_refresh_request") as acknowledge:
                requested.tick(time.monotonic())
            acknowledge.assert_not_called()


class RefreshOptionTests(unittest.TestCase):
    def test_reset_preserves_all_options_and_secret_references(self):
        options = {"uuid": "!secret aero_uuid", "beast_host": "my-receiver", "refresh_upstream": True}
        response = lambda data: Response(json.dumps({"result": "ok", "data": data}).encode())
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-token"}), patch.object(refresh, "build_opener") as build:
            build.return_value.open.side_effect = [response({"options": options}), response({})]
            self.assertTrue(refresh.clear_refresh_request())
            get, post = [call.args[0] for call in build.return_value.open.call_args_list]
        self.assertEqual(get.full_url, "http://supervisor/addons/self/info")
        self.assertEqual(post.full_url, "http://supervisor/addons/self/options")
        self.assertEqual(post.get_method(), "POST")
        payload = json.loads(post.data)
        self.assertEqual(payload, {"options": {**options, "refresh_upstream": False}})

    def test_does_not_overwrite_when_user_has_already_cleared_flag(self):
        data = {"result": "ok", "data": {"options": {"uuid": UUID, "refresh_upstream": False}}}
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-token"}), patch.object(refresh, "build_opener") as build:
            build.return_value.open.return_value = Response(json.dumps(data).encode())
            self.assertTrue(refresh.clear_refresh_request())
            self.assertEqual(build.return_value.open.call_count, 1)

    def test_missing_token_does_not_call_api(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(refresh, "build_opener") as build:
            self.assertFalse(refresh.clear_refresh_request())
            build.assert_not_called()

    def test_api_failure_keeps_current_options_and_does_not_log_secrets(self):
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "private-token"}), patch.object(refresh, "build_opener") as build:
            build.return_value.open.side_effect = URLError("private-token")
            with self.assertLogs("aeronexus", level="WARNING") as logs:
                self.assertFalse(refresh.clear_refresh_request())
            self.assertNotIn("private-token", "\n".join(logs.output))

    def test_redirect_failure_is_handled_without_crashing_worker_manager(self):
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-token"}), patch.object(refresh, "build_opener") as build:
            build.return_value.open.side_effect = relay.DiscoveryError("redirect")
            self.assertFalse(refresh.clear_refresh_request())


class OfficialWorkerTests(unittest.TestCase):
    def test_full_official_relay_forwards_uuid_adsb_and_excludes_mlat(self):
        source, destination = listener(), listener()
        settings = relay.Settings(UUID, "127.0.0.1", source.getsockname()[1])
        candidate = upstream.identify(ORIGINAL, "127.0.0.1", destination.getsockname()[1])
        worker = manager.Worker(settings)
        sockets = []
        try:
            with self.assertLogs("aeronexus", level="INFO") as logs:
                worker.start(candidate, settings.beast_host, settings.beast_port)
                up, _ = destination.accept()
                sockets.append(up)
                up.settimeout(5)
                self.assertEqual(exact(up, 38), b"\x1a\xe4" + UUID.encode())
                src, _ = source.accept()
                sockets.append(src)
                good = frame(17) + frame(18)
                src.sendall(frame(11) + frame(17, timestamp=b"\xff\x00MLAT") + good)
                self.assertEqual(exact(up, len(good)), good)
                worker.stop()
            rendered = "\n".join(logs.output)
            self.assertNotIn(UUID, rendered)
            self.assertNotIn(UUID[:8], rendered)
        finally:
            worker.stop()
            for sock in sockets: sock.close()
            source.close()
            destination.close()


if __name__ == "__main__": unittest.main(verbosity=2)
