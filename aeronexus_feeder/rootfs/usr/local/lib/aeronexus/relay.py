#!/usr/bin/env python3
"""Home Assistant app adapter for the supplied AeroNexus Python Beast relay.

Protocol/parser provenance is recorded in NOTICE.md. This program never modifies
another app, starts a decoder, or listens on a TCP port.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import select
import signal
import socket
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from beast import HB, Splitter, uuid_frame

LOG = logging.getLogger("aeronexus")
FEED_HOST = "aeronexus.kr"
FEED_PORT = 30004
HEARTBEAT_S = 30.0
SOCKET_TIMEOUT = 5.0
STABLE_S = 60.0
UUID_PATTERN = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
SLUG_PATTERN = re.compile(r"[A-Za-z0-9_.-]+")


class ConfigError(ValueError):
    pass


class DiscoveryError(RuntimeError):
    pass


class StopRequested(BaseException):
    pass


@dataclass(frozen=True)
class Settings:
    uuid: str = ""
    beast_host: str = ""
    beast_port: int = 30005
    filter: str = "adsb"
    stats_interval: int = 60
    update_interval: int = 3600  # Legacy 1.1.0 option; ignored by the manager.

    @classmethod
    def load(cls, path: Path) -> Settings:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ConfigError("Cannot read valid options JSON; save Configuration and restart.") from None
        if not isinstance(data, dict):
            raise ConfigError("Options must be a JSON object.")
        unknown = set(data) - {"uuid", "beast_host", "beast_port", "filter", "stats_interval", "update_interval"}
        if unknown:
            raise ConfigError("Unknown option keys; compare with the app schema.")
        u = data.get("uuid", "")
        if not isinstance(u, str) or (u and not UUID_PATTERN.fullmatch(u)):
            raise ConfigError("UUID must be empty or a canonical 36-character UUID (8-4-4-4-12).")
        host = data.get("beast_host", "")
        if not isinstance(host, str) or any(c.isspace() or ord(c) < 32 for c in host):
            raise ConfigError("beast_host must be a host name or IP address, without whitespace.")
        if any(c in host for c in "/\\@[]"):
            raise ConfigError("beast_host must not include a URL, brackets, credentials, or port.")
        if ":" in host:
            try:
                ipaddress.IPv6Address(host)
            except ValueError:
                raise ConfigError("Use beast_port separately; only IPv6 addresses may contain colons.") from None
        port = data.get("beast_port", 30005)
        interval = data.get("stats_interval", 60)
        update_interval = data.get("update_interval", 3600)
        if type(port) is not int or not 1 <= port <= 65535:
            raise ConfigError("beast_port must be between 1 and 65535.")
        if type(interval) is not int or not 30 <= interval <= 3600:
            raise ConfigError("stats_interval must be between 30 and 3600 seconds.")
        if type(update_interval) is not int or not 300 <= update_interval <= 86400:
            raise ConfigError("update_interval must be between 300 and 86400 seconds.")
        mode = data.get("filter", "adsb")
        if mode not in ("adsb", "all"):
            raise ConfigError("filter must be adsb or all.")
        return cls(u.lower(), host, port, mode, interval, update_interval)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DiscoveryError("Supervisor redirected the request; refusing to forward its token.")


def supervisor_info() -> dict:
    """GET only; default Supervisor role can read /supervisor/info.

    The unversioned v1 response currently includes installed apps. Do not call
    GET /addons: it requires the broader manager role. If this legacy response
    field is removed in future, the explicit beast_host option still works.
    """
    token = os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN")
    if not token:
        raise DiscoveryError("Supervisor token is unavailable; set beast_host explicitly.")
    req = Request("http://supervisor/supervisor/info", headers={"Authorization": f"Bearer {token}"})
    try:
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with opener.open(req, timeout=SOCKET_TIMEOUT) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise DiscoveryError("Supervisor response exceeds the size limit.")
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get("result") != "ok":
            raise DiscoveryError("Supervisor did not return a successful response.")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise DiscoveryError("Supervisor returned invalid metadata.")
        return data
    except (HTTPError, URLError, OSError, ValueError) as exc:
        # Do not print a response body, options, UUID, or API token.
        raise DiscoveryError(f"Supervisor discovery failed ({type(exc).__name__}); set beast_host if needed.") from None


def choose_source(data: dict) -> str:
    apps = data.get("addons")
    if not isinstance(apps, list):
        raise DiscoveryError("Installed-app metadata is unavailable; set beast_host explicitly.")
    slugs = sorted({a["slug"] for a in apps if isinstance(a, dict)
                    and isinstance(a.get("slug"), str)
                    and a["slug"].endswith("_adsb-multi-portal-feeder")
                    and SLUG_PATTERN.fullmatch(a["slug"])})
    if not slugs:
        raise DiscoveryError("ADS-B Multi-Portal Feeder is not installed under its standard slug; set beast_host.")
    if len(slugs) > 1:
        raise DiscoveryError("Multiple ADS-B Multi-Portal Feeders found; select one with beast_host.")
    return slugs[0].replace("_", "-")


class SourceResolver:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cached = ""
        self.expires = 0.0

    def resolve(self) -> tuple[str, int]:
        if self.settings.beast_host:
            return self.settings.beast_host, self.settings.beast_port
        now = time.monotonic()
        if not self.cached or now >= self.expires:
            host = choose_source(supervisor_info())
            if host != self.cached:
                LOG.info("Auto-selected Beast source: %s:%d", host, self.settings.beast_port)
            self.cached = host
            self.expires = now + 60.0
        return self.cached, self.settings.beast_port


class Backoff:
    def __init__(self):
        self.delay = 2.0
        self.next = 0.0
        self.since = 0.0

    def connected(self, now: float):
        self.since = now

    def retry(self, now: float, was_connected: bool = False) -> float:
        if was_connected and now - self.since >= STABLE_S:
            self.delay = 2.0
        delay = self.delay
        self.next = now + delay
        self.delay = min(delay * 2.0, 60.0)
        return delay


def connect(host: str, port: int) -> socket.socket:
    sock = socket.create_connection((host, port), timeout=SOCKET_TIMEOUT)
    try:
        # Bound sendall: a server that stops reading must not freeze the relay.
        sock.settimeout(SOCKET_TIMEOUT)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        return sock
    except BaseException:
        sock.close()
        raise


def close(sock):
    if sock is not None:
        sock.close()


class Relay:
    def __init__(self, settings: Settings, resolver=None, *, feed_host=FEED_HOST, feed_port=FEED_PORT):
        self.settings = settings
        self.resolver = resolver or SourceResolver(settings)
        # Overrides are for local tests only; the UI fixes the destination.
        self.feed_host, self.feed_port = feed_host, feed_port
        self.src = self.up = None
        self.src_retry, self.up_retry = Backoff(), Backoff()
        self.sp = Splitter(settings.filter)
        self.last_tx = self.last_stat = time.monotonic()
        self.sent = self.tx_bytes = self.offline = 0

    def drop_up(self, reason: str):
        close(self.up)
        self.up = None
        delay = self.up_retry.retry(time.monotonic(), was_connected=True)
        LOG.warning("%s; retry in %.0fs", reason, delay)

    def run(self, stop=lambda: False):
        LOG.info("Starting relay; destination=%s:%d filter=%s (UUID hidden)",
                 self.feed_host, self.feed_port, self.settings.filter)
        try:
            while not stop():
                now = time.monotonic()
                if self.src is None and now >= self.src_retry.next:
                    try:
                        host, port = self.resolver.resolve()
                        self.src = connect(host, port)
                        self.src_retry.connected(time.monotonic())
                        self.sp.buf = b""  # Never join partial frames from two TCP sessions.
                        LOG.info("Beast connected: %s:%d", host, port)
                    except (OSError, DiscoveryError) as exc:
                        delay = self.src_retry.retry(time.monotonic())
                        LOG.warning("Beast unavailable: %s; retry in %.0fs", exc, delay)
                now = time.monotonic()
                if self.up is None and self.src is not None and now >= self.up_retry.next:
                    candidate = None
                    try:
                        candidate = connect(self.feed_host, self.feed_port)
                        candidate.sendall(uuid_frame(self.settings.uuid))
                        self.up = candidate
                        self.up_retry.connected(time.monotonic())
                        self.last_tx = time.monotonic()
                        LOG.info("AeroNexus TCP connected; UUID frame sent (server acceptance is not confirmed)")
                    except OSError as exc:
                        close(candidate)
                        delay = self.up_retry.retry(time.monotonic())
                        LOG.warning("AeroNexus unavailable: %s; retry in %.0fs", exc, delay)
                ready = [s for s in (self.src, self.up) if s is not None]
                if ready:
                    readable, _, _ = select.select(ready, [], [], 1.0)
                else:
                    time.sleep(1.0)
                    readable = []
                if self.src is not None and self.src in readable:
                    try:
                        chunk = self.src.recv(65536)
                    except OSError:
                        chunk = b""
                    if not chunk:
                        close(self.src)
                        self.src = None
                        self.sp.buf = b""
                        delay = self.src_retry.retry(time.monotonic(), was_connected=True)
                        LOG.warning("Beast disconnected; retry in %.0fs", delay)
                    else:
                        previous = self.sp.n_out
                        outgoing = self.sp.feed(chunk)
                        frames = self.sp.n_out - previous
                        if outgoing and self.up is not None:
                            try:
                                self.up.sendall(outgoing)
                                self.sent += frames
                                self.tx_bytes += len(outgoing)
                                self.last_tx = time.monotonic()
                            except OSError:
                                self.drop_up("AeroNexus send failed (including timeout)")
                                self.offline += frames
                        elif outgoing:
                            self.offline += frames
                if self.up is not None and self.up in readable:
                    try:
                        data = self.up.recv(4096)
                    except OSError:
                        data = b""
                    if not data:
                        self.drop_up("AeroNexus disconnected; check UUID registration or duplicate use")
                now = time.monotonic()
                if self.up is not None and now - self.last_tx >= HEARTBEAT_S:
                    try:
                        self.up.sendall(HB)
                        self.last_tx = time.monotonic()
                    except OSError:
                        self.drop_up("AeroNexus heartbeat failed")
                if now - self.last_stat >= self.settings.stats_interval:
                    LOG.info("Stats: input=%d eligible=%d sent=%d offline_or_failed=%d bytes=%d mlat_dropped=%d resync=%d source=%s upstream=%s",
                             self.sp.n_in, self.sp.n_out, self.sent, self.offline, self.tx_bytes,
                             self.sp.n_mlat, self.sp.n_resync,
                             "up" if self.src else "down", "up" if self.up else "down")
                    if not self.sp.n_in:
                        LOG.warning("No complete Beast frames in this interval; check the decoder/output/antenna.")
                    self.sp.n_in = self.sp.n_out = self.sp.n_mlat = self.sp.n_resync = 0
                    self.sp.df = {}
                    self.sent = self.offline = self.tx_bytes = 0
                    self.last_stat = now
        finally:
            close(self.src)
            close(self.up)
            self.src = self.up = None
            LOG.info("Relay stopped; sockets closed")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--options", type=Path, default=Path("/data/options.json"))
    args = parser.parse_args()

    def request_stop(_signum, _frame):
        raise StopRequested()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        settings = Settings.load(args.options)
        if not settings.uuid:
            LOG.warning("UUID is empty. Waiting without network connections. Enter UUID in Configuration, Save, then Restart.")
            while True:
                time.sleep(60)
        Relay(settings).run()
    except ConfigError as exc:
        LOG.error("Configuration error: %s", exc)
        return 2
    except StopRequested:
        LOG.info("Stop requested")
    return 0


if __name__ == "__main__":
    sys.exit(main())
