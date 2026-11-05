"""No image-bundled relay: obtain full installers directly and compare contents."""
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

APP = Path(__file__).resolve().parents[1]
LIB = APP / "rootfs/usr/local/lib/aeronexus"
sys.path.insert(0, str(LIB))
import manager
import relay
import upstream
from test_relay import UUID
from test_upstream import FakeWorker, ORIGINAL, Resolver, Response, installer, official


class OfficialDownloadTests(unittest.TestCase):
    def test_fresh_install_has_no_image_bundled_relay_to_run(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(upstream.VersionStore(Path(directory)).working())
        self.assertFalse((LIB / "bundled_relay.py").exists())

    def test_legacy_bundled_cache_is_skipped_and_forces_official_check(self):
        with tempfile.TemporaryDirectory() as directory:
            store = upstream.VersionStore(Path(directory))
            store.activate(upstream.identify(ORIGINAL))  # Old bundled metadata: no official script digest.
            store.state["checked_app_version"] = manager.APP_VERSION
            app = manager.Manager(relay.Settings(UUID), store, Resolver(), FakeWorker())
            self.assertIsNone(app.active)
            self.assertTrue(app.check_pending)

    def test_wrong_source_url_and_corrupt_metadata_are_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = upstream.VersionStore(Path(directory))
            candidate = official()
            store.activate(candidate)
            store.state["versions"][candidate.release_id]["source_url"] = "https://github.com/elsewhere/relay.py"
            self.assertIsNone(store.load(candidate.release_id))
            store.state["versions"][candidate.release_id] = 42
            self.assertIsNone(store.load(candidate.release_id))

    def test_first_start_downloads_and_runs_the_received_code(self):
        with tempfile.TemporaryDirectory() as directory:
            store = upstream.VersionStore(Path(directory))
            worker = FakeWorker()
            app = manager.Manager(relay.Settings(UUID), store, Resolver(), worker)
            body = installer(ORIGINAL + b"\n# newly received from official server\n")
            expected = upstream.extract(body)
            self.assertIsNone(app.active)
            with patch.object(upstream, "build_opener") as build:
                build.return_value.open.return_value = Response(body)
                app.tick(time.monotonic())
                self.assertEqual(build.return_value.open.call_args.args[0].full_url, "https://aeronexus.kr/feed.sh")
            self.assertEqual(worker.started, [expected.release_id])
            self.assertIsNone(app.active)  # Do not activate until probation completes.
            app.tick(app.probation_until + 1)
            self.assertEqual(app.active.code, expected.code)
            self.assertEqual((Path(directory) / "feed.sh").read_bytes(), body)

    def test_first_download_failure_never_runs_a_github_copy_or_probes_beast(self):
        with tempfile.TemporaryDirectory() as directory:
            store = upstream.VersionStore(Path(directory))
            worker, resolver = FakeWorker(), Mock()
            app = manager.Manager(relay.Settings(UUID), store, resolver, worker)
            with patch.object(upstream, "build_opener") as build:
                build.return_value.open.side_effect = URLError("offline")
                app.tick(time.monotonic())
                app.tick(time.monotonic() + 86400)
                self.assertEqual(build.return_value.open.call_count, 1)
            self.assertEqual(worker.started, [])
            resolver.resolve.assert_not_called()
            self.assertNotIn("checked_app_version", store.state)
            self.assertTrue(manager.Manager(relay.Settings(UUID), store, Resolver(), FakeWorker()).check_pending)

    def test_invalid_download_preserves_the_previous_official_code_and_file(self):
        with tempfile.TemporaryDirectory() as directory:
            store = upstream.VersionStore(Path(directory))
            with patch.object(upstream, "build_opener") as build:
                build.return_value.open.return_value = Response(installer())
                previous = store.check()
                store.activate(previous)
                build.return_value.open.return_value = Response(installer(b"not valid python !\n"))
                with self.assertRaises(upstream.UpdateError):
                    store.check()
            self.assertEqual(store.working().release_id, previous.release_id)
            self.assertEqual((Path(directory) / "feed.sh").read_bytes(), installer())

    def test_installer_only_change_does_not_restart_unchanged_python(self):
        with tempfile.TemporaryDirectory() as directory:
            store = upstream.VersionStore(Path(directory))
            store.activate(official())
            worker = FakeWorker()
            app = manager.Manager(relay.Settings(UUID), store, Resolver(), worker)
            changed = installer().replace(b"#!/bin/bash\n", b"#!/bin/bash\n# installer-only edit\n")
            with patch.object(upstream, "build_opener") as build:
                build.return_value.open.return_value = Response(installer())
                app.tick(time.monotonic())
                build.return_value.open.return_value = Response(changed)
                app.check()
                app.tick(time.monotonic())
            self.assertEqual(len(worker.started), 1)
            self.assertIsNone(app.pending)
            self.assertEqual(store.state["script_sha256"], upstream.extract(changed).script_sha256)
            self.assertEqual((Path(directory) / "feed.sh").read_bytes(), changed)

    def test_changed_python_replaces_running_code_after_probation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = upstream.VersionStore(Path(directory))
            previous = official()
            store.activate(previous)
            worker = FakeWorker()
            app = manager.Manager(relay.Settings(UUID), store, Resolver(), worker)
            newer = installer(ORIGINAL + b"\n# official code update\n")
            with patch.object(upstream, "build_opener") as build:
                build.return_value.open.return_value = Response(newer)
                app.tick(time.monotonic())
            app.tick(app.probation_until + 1)
            self.assertEqual(app.active.code, upstream.extract(newer).code)
            self.assertEqual(store.state["previous"], previous.release_id)

    def test_unrequested_304_is_not_a_successful_content_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            store = upstream.VersionStore(Path(directory))
            with patch.object(upstream, "build_opener") as build:
                build.return_value.open.side_effect = HTTPError(upstream.SOURCE_URL, 304, "", {}, None)
                with self.assertRaises(upstream.UpdateError):
                    store.check()
            self.assertIsNone(store.working())

    def test_missing_cache_forces_download_even_if_app_version_was_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            store = upstream.VersionStore(Path(directory))
            store.state["checked_app_version"] = manager.APP_VERSION
            app = manager.Manager(relay.Settings(UUID), store, Resolver(), FakeWorker())
            self.assertTrue(app.check_pending)

    def test_first_candidate_crash_stays_idle_without_a_fallback_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            store = upstream.VersionStore(Path(directory))
            worker = FakeWorker()
            app = manager.Manager(relay.Settings(UUID), store, Resolver(), worker)
            with patch.object(upstream, "build_opener") as build:
                build.return_value.open.return_value = Response(installer())
                app.tick(time.monotonic())
            worker.running, worker.code = False, 1
            app.tick(time.monotonic())
            app.tick(time.monotonic() + 86400)
            self.assertEqual(len(worker.started), 1)
            self.assertIsNone(app.active)
            self.assertIsNone(app.pending)


if __name__ == "__main__":
    unittest.main(verbosity=2)
