#!/usr/bin/env python3
"""Check upstream once per installed app version, then run the pinned relay."""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from relay import ConfigError, DiscoveryError, Settings, SourceResolver
from upstream import RUNNER, Candidate, UpdateError, VersionStore, child_environment, child_identity
from app_version import APP_VERSION

LOG = logging.getLogger("aeronexus")
PROBATION = 30.0


class Worker:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.process = None
        self.reader = None

    def start(self, candidate: Candidate, host: str, port: int):
        self.stop()
        env = child_environment(self.settings.uuid, host, port, self.settings.filter,
                                candidate, self.settings.stats_interval)
        self.process = subprocess.Popen(
            [sys.executable, "-I", "-u", "-B", str(RUNNER), "--run"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=env, cwd="/tmp" if os.name == "posix" else None,
            start_new_session=(os.name == "posix"), **child_identity())
        process = self.process

        def forward_logs():
            for data in iter(lambda: process.stdout.readline(4096), b""):
                text = data.decode("utf-8", "replace").rstrip()
                for value in (self.settings.uuid, self.settings.uuid.upper(),
                              self.settings.uuid[:8], self.settings.uuid[:8].upper()):
                    if value:
                        text = text.replace(value, "[UUID hidden]")
                LOG.info("upstream: %s", text)

        self.reader = threading.Thread(target=forward_logs, daemon=True)
        self.reader.start()
        try:
            process.stdin.write(candidate.code)
            process.stdin.close()
        except (OSError, BrokenPipeError):
            self.stop()
            raise UpdateError("Official relay exited before receiving its source") from None
        LOG.info("Official relay running: code=%s endpoint=%s:%d Beast=%s:%d",
                 candidate.sha256[:12], candidate.feed_host, candidate.feed_port, host, port)

    def alive(self):
        return self.process is not None and self.process.poll() is None

    def stop(self):
        process = self.process
        if process is not None:
            if process.poll() is None:
                try:
                    if os.name == "posix":
                        os.killpg(process.pid, signal.SIGTERM)
                    else:
                        process.terminate()
                    process.wait(timeout=7)
                except (OSError, subprocess.TimeoutExpired):
                    try:
                        if os.name == "posix":
                            os.killpg(process.pid, signal.SIGKILL)
                        else:
                            process.kill()
                    except OSError:
                        pass
                    process.wait(timeout=5)
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            if self.reader:
                self.reader.join(timeout=2)
            if process.stdout:
                process.stdout.close()
        self.process = None
        self.reader = None


class Manager:
    def __init__(self, settings: Settings, store: VersionStore, resolver=None, worker=None,
                 app_version=APP_VERSION):
        self.settings, self.store = settings, store
        self.resolver = resolver or SourceResolver(settings)
        self.worker = worker or Worker(settings)
        self.active = store.working()
        self.app_version = app_version
        self.check_pending = store.state.get("checked_app_version") != app_version
        self.pending = None
        self.probation_until = None
        self.endpoint = None
        self.next_resolve = self.next_start = 0.0
        self.restart_delay = 2.0
        if self.check_pending:
            # A new HA adapter may be compatible with a previously rejected relay.
            store.state.pop("rejected", None)
        else:
            latest = store.state.get("latest")
            if latest != self.active.release_id and latest != store.state.get("rejected"):
                self.pending = store.load(latest)

    def check(self):
        try:
            candidate = self.store.check()
            if candidate and candidate.release_id != self.active.release_id:
                self.store.save(candidate)
                self.store.state["latest"] = candidate.release_id
                self.pending = candidate
                self.probation_until = None
                LOG.info("New official relay downloaded and validated: %s", candidate.sha256[:12])
            self.store.state["checked_app_version"] = self.app_version
            self.store.save_state()
        except (UpdateError, OSError) as exc:
            LOG.warning("Upstream update not applied: %s; keeping code=%s", exc, self.active.sha256[:12])
            LOG.info("No periodic retry; restart the app to retry this initial check")

    def tick(self, now: float):
        if self.check_pending:
            self.check_pending = False
            self.check()
        if now >= self.next_resolve:
            try:
                endpoint = self.resolver.resolve()
                if endpoint != self.endpoint:
                    self.worker.stop()
                    self.endpoint = endpoint
                    self.probation_until = None
                    self.next_start = 0
            except (DiscoveryError, OSError) as exc:
                LOG.warning("Beast source discovery: %s", exc)
            self.next_resolve = time.monotonic() + 30

        if self.pending is not None and self.probation_until is None and self.endpoint:
            try:
                self.worker.start(self.pending, *self.endpoint)
                self.probation_until = time.monotonic() + PROBATION
            except (OSError, UpdateError) as exc:
                LOG.warning("New relay could not start: %s; rolling back", exc)
                self.store.reject(self.pending)
                self.pending = None
                self.next_start = 0

        if self.probation_until is not None:
            if not self.worker.alive():
                LOG.warning("New relay exited during its 30-second startup check; rolling back to %s", self.active.sha256[:12])
                self.store.reject(self.pending)
                self.pending = None
                self.probation_until = None
                self.worker.stop()
                self.next_start = 0
            elif now >= self.probation_until:
                self.store.activate(self.pending)
                self.active = self.pending
                self.pending = None
                self.probation_until = None
                self.restart_delay = 2.0
                LOG.info("Official relay update active: %s", self.active.sha256[:12])

        if self.probation_until is None and not self.worker.alive() and self.endpoint and now >= self.next_start:
            try:
                self.worker.start(self.active, *self.endpoint)
            except (OSError, UpdateError) as exc:
                LOG.warning("Relay start failed: %s", exc)
            self.next_start = time.monotonic() + self.restart_delay
            self.restart_delay = min(self.restart_delay * 2, 60.0)

    def run(self, stopped: threading.Event):
        LOG.info("Official upstream policy: check once per app version (%s), no periodic polling", self.app_version)
        if not self.check_pending:
            LOG.info("Upstream already checked for this app version; using cached code=%s", self.active.sha256[:12])
        try:
            while not stopped.is_set():
                self.tick(time.monotonic())
                stopped.wait(1)
        finally:
            self.worker.stop()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--options", type=Path, default=Path("/data/options.json"))
    parser.add_argument("--cache", type=Path, default=Path("/data/upstream"))
    args = parser.parse_args()
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    try:
        settings = Settings.load(args.options)
        if not settings.uuid:
            LOG.warning("UUID is empty. Waiting without network connections. Enter UUID, Save, then Restart.")
            while not stopped.wait(1):
                pass
            return 0
        manager = Manager(settings, VersionStore(args.cache))
        manager.run(stopped)
    except (ConfigError, UpdateError, OSError) as exc:
        LOG.error("App startup failed: %s", exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
