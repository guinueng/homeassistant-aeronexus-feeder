"""Permanent stop during one app run, Supervisor self-stop and manual recovery."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError

APP = Path(__file__).resolve().parents[1]
LIB = APP / "rootfs/usr/local/lib/aeronexus"
sys.path.insert(0, str(LIB))
import engine_runner
import manager
import relay
import shutdown
import upstream
from test_relay import UUID
from test_upstream import FakeWorker, ORIGINAL, Resolver, Response, official


class StopPolicyTests(unittest.TestCase):
    def make_manager(self, directory):
        store = upstream.VersionStore(Path(directory))
        store.activate(official())
        worker = FakeWorker()
        app = manager.Manager(relay.Settings(UUID), store, Resolver(), worker)
        return app, worker, store

    def test_active_uuid_exit_never_restarts_or_checks_network_again(self):
        with tempfile.TemporaryDirectory() as directory:
            app, worker, store = self.make_manager(directory)
            with patch.object(store, "check", return_value=app.active):
                app.tick(time.monotonic())
            worker.running, worker.code = False, engine_runner.UUID_CONFLICT_EXIT
            with patch.object(store, "check") as check, patch.object(app.resolver, "resolve") as resolve:
                app.tick(time.monotonic())
                app.tick(time.monotonic() + 86400)
            self.assertTrue(app.connection_stopped)
            self.assertEqual(len(worker.started), 1)
            check.assert_not_called()
            resolve.assert_not_called()

    def test_candidate_uuid_exit_does_not_roll_back_and_reconnect(self):
        with tempfile.TemporaryDirectory() as directory:
            app, worker, store = self.make_manager(directory)
            newer = official(ORIGINAL + b"\n# new candidate\n")
            active = app.active.release_id
            with patch.object(store, "check", return_value=newer):
                app.tick(time.monotonic())
            worker.running, worker.code = False, engine_runner.UUID_CONFLICT_EXIT
            app.tick(time.monotonic())
            self.assertEqual(worker.started, [newer.release_id])
            self.assertEqual(store.state["active"], active)
            self.assertEqual(store.state["latest"], newer.release_id)
            self.assertNotIn("rejected", store.state)
            self.assertTrue(app.connection_stopped)

    def test_immediate_candidate_exit_is_detected_before_probation_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            app, worker, store = self.make_manager(directory)
            newer = official(ORIGINAL + b"\n# new candidate\n")
            original_start = worker.start
            def rejected_start(*args):
                original_start(*args)
                worker.running, worker.code = False, engine_runner.UUID_CONFLICT_EXIT
            with patch.object(store, "check", return_value=newer), patch.object(worker, "start", side_effect=rejected_start):
                app.tick(time.monotonic())
            self.assertTrue(app.connection_stopped)
            self.assertEqual(worker.started, [newer.release_id])
            self.assertNotIn("rejected", store.state)

    def test_exit_during_discovery_is_not_lost_when_source_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            app, worker, store = self.make_manager(directory)
            with patch.object(store, "check", return_value=app.active):
                app.tick(time.monotonic())
            def resolve():
                worker.running, worker.code = False, engine_runner.UUID_CONFLICT_EXIT
                return ("different-source", 30005)
            with patch.object(app.resolver, "resolve", side_effect=resolve):
                app.tick(app.next_resolve + 1)
            self.assertTrue(app.connection_stopped)
            self.assertEqual(len(worker.started), 1)

    def test_other_worker_exit_retains_normal_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            app, worker, store = self.make_manager(directory)
            with patch.object(store, "check", return_value=app.active):
                app.tick(time.monotonic())
            worker.running, worker.code = False, 1
            app.tick(app.next_start + 1)
            self.assertFalse(app.connection_stopped)
            self.assertEqual(len(worker.started), 2)

    def test_supervisor_stop_is_requested_once_and_failure_stays_idle(self):
        for accepted in [True, False]:
            with self.subTest(accepted=accepted), tempfile.TemporaryDirectory() as directory:
                app, worker, _ = self.make_manager(directory)
                worker.code = engine_runner.UUID_CONFLICT_EXIT
                stopped, requested = threading.Event(), threading.Event()
                def stop_app():
                    requested.set()
                    return accepted
                thread = threading.Thread(target=app.run, args=(stopped,), daemon=True)
                with patch.object(manager, "request_app_stop", side_effect=stop_app) as request:
                    try:
                        thread.start()
                        self.assertTrue(requested.wait(3))
                        self.assertTrue(thread.is_alive(), "Wait for Supervisor/SIGTERM; do not crash into watchdog restart")
                        app.tick(time.monotonic() + 86400)
                        self.assertEqual(worker.started, [])
                        request.assert_called_once_with()
                    finally:
                        stopped.set()
                        thread.join(timeout=3)
                self.assertFalse(thread.is_alive())

    def test_manual_new_app_run_can_attempt_connection_again(self):
        with tempfile.TemporaryDirectory() as directory:
            app, worker, store = self.make_manager(directory)
            worker.code = engine_runner.UUID_CONFLICT_EXIT
            app.tick(time.monotonic())
            new_worker = FakeWorker()
            restarted = manager.Manager(relay.Settings(UUID), store, Resolver(), new_worker)
            with patch.object(store, "check", return_value=restarted.active):
                restarted.tick(time.monotonic())
            self.assertFalse(restarted.connection_stopped)
            self.assertEqual(len(new_worker.started), 1)


class SupervisorStopTests(unittest.TestCase):
    def test_request_stops_only_self_without_changing_user_options(self):
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "private-token"}), patch.object(shutdown, "build_opener") as build:
            build.return_value.open.return_value = Response(b'{"result":"ok","data":{}}')
            self.assertTrue(shutdown.request_app_stop())
            request = build.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, "http://supervisor/addons/self/stop")
            self.assertEqual(request.get_method(), "POST")
            self.assertEqual(json.loads(request.data), {})
            self.assertEqual(build.return_value.open.call_count, 1)

    def test_missing_token_keeps_relay_stopped_without_api_calls(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(shutdown, "build_opener") as build:
            self.assertFalse(shutdown.request_app_stop())
            build.assert_not_called()

    def test_api_errors_and_redirects_do_not_log_secrets_or_raise(self):
        for error in [URLError("private-token " + UUID), relay.DiscoveryError("redirect")]:
            with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "private-token"}), patch.object(shutdown, "build_opener") as build:
                build.return_value.open.side_effect = error
                with self.assertLogs("aeronexus", level="WARNING") as logs:
                    self.assertFalse(shutdown.request_app_stop())
                self.assertNotIn("private-token", "\n".join(logs.output))
                self.assertNotIn(UUID, "\n".join(logs.output))

    def test_invalid_or_oversize_response_is_not_treated_as_success(self):
        for data in [b'[]', b'{"result":"error"}', b'x' * 65537]:
            with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "private-token"}), patch.object(shutdown, "build_opener") as build:
                build.return_value.open.return_value = Response(data)
                self.assertFalse(shutdown.request_app_stop())


if __name__ == "__main__":
    unittest.main(verbosity=2)
