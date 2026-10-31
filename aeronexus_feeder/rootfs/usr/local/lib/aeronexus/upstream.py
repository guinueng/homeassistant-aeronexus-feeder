"""Fetch, validate and retain official AeroNexus relay versions.

Only the Python here-document is executed. The host installation shell is data.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

LOG = logging.getLogger("aeronexus")
SOURCE_URL = "https://aeronexus.kr/feed.sh"
MAX_SCRIPT = 2 * 1024 * 1024
MAX_RELAY = 512 * 1024
TIMEOUT = 15
HASH = re.compile(r"[0-9a-f]{64}")
RUNNER = Path(__file__).with_name("engine_runner.py")
BUNDLED = Path(__file__).with_name("bundled_relay.py")


class UpdateError(RuntimeError):
    pass


class OfficialOriginOnly(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        from urllib.parse import urlsplit
        parsed = urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname != "aeronexus.kr" or parsed.port not in (None, 443):
            raise UpdateError("Official feed.sh redirected outside its HTTPS origin")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass(frozen=True)
class Candidate:
    code: bytes
    sha256: str
    feed_host: str = "aeronexus.kr"
    feed_port: int = 30004
    script_sha256: str = ""

    @property
    def release_id(self):
        identity = f"{self.sha256}\0{self.feed_host}\0{self.feed_port}".encode()
        return hashlib.sha256(identity).hexdigest()


def identify(code: bytes, host="aeronexus.kr", port=30004, script_sha="") -> Candidate:
    if not code or len(code) > MAX_RELAY:
        raise UpdateError("Relay source has an invalid size")
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, UnicodeError):
        raise UpdateError("Downloaded relay is not valid Python") from None
    functions = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    if not {"uuid_frame", "Splitter", "main"} <= functions:
        raise UpdateError("Official relay interface changed; retaining the working version")
    return Candidate(code, hashlib.sha256(code).hexdigest(), host, port, script_sha)


def extract(script: bytes) -> Candidate:
    if not script or len(script) > MAX_SCRIPT:
        raise UpdateError("Official installer has an invalid size")
    try:
        text = script.decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeError:
        raise UpdateError("Official installer is not UTF-8") from None
    if not text.startswith("#!/"):
        raise UpdateError("Expected the official shell installer, not HTML or an error page")
    matches = list(re.finditer(r"(?m)^[ \t]*cat[^\n]*<<[ \t]*['\"]?PYEOF['\"]?[ \t]*\n", text))
    if len(matches) != 1:
        raise UpdateError("Cannot uniquely locate the official Python relay")
    start = matches[0].end()
    ending = re.search(r"(?m)^PYEOF[ \t]*$", text[start:])
    if ending is None:
        raise UpdateError("Official Python relay is truncated")
    code = text[start:start + ending.start()].encode("utf-8")
    host = re.search(r'(?m)^FEED_HOST="\$\{AERO_FEED_HOST:-([A-Za-z0-9.-]+)\}"[ \t]*$', text)
    port = re.search(r'(?m)^FEED_PORT="\$\{AERO_FEED_PORT:-([0-9]+)\}"[ \t]*$', text)
    if not host or not port or not 1 <= int(port[1]) <= 65535:
        raise UpdateError("Official destination configuration changed; retaining the working version")
    return identify(code, host[1], int(port[1]), hashlib.sha256(script).hexdigest())


def child_identity() -> dict:
    if os.name == "posix" and os.geteuid() == 0:
        import pwd
        import grp
        return {"user": pwd.getpwnam("aeronexus").pw_uid,
                "group": grp.getgrnam("aeronexus").gr_gid, "extra_groups": []}
    return {}


def child_environment(uuid: str, beast_host: str, beast_port: int, mode: str,
                      candidate: Candidate, stats_interval=60) -> dict[str, str]:
    # The downloaded code does not receive the Supervisor token or parent env.
    env = {"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1", "UUID": uuid,
            "BEAST_HOST": beast_host, "BEAST_PORT": str(beast_port),
            "FEED_HOST": candidate.feed_host, "FEED_PORT": str(candidate.feed_port),
            "FILTER": mode, "AERO_STAT_S": str(stats_interval)}
    if os.name == "nt" and "SystemRoot" in os.environ:
        env["SystemRoot"] = os.environ["SystemRoot"]
    return env


def validate(candidate: Candidate):
    env = child_environment("12345678-1234-4321-8765-123456789abc", "127.0.0.1", 30005, "adsb", candidate)
    try:
        result = subprocess.run([sys.executable, "-I", "-B", str(RUNNER), "--validate"],
                                input=candidate.code, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=10, env=env, cwd=os.environ.get("TMPDIR", "/tmp") if os.name == "posix" else None,
                                **child_identity())
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError(f"Relay compatibility check could not complete ({type(exc).__name__})") from None
    if result.returncode != 0 or b'"aeronexus_validation": "ok"' not in result.stdout:
        raise UpdateError("Relay failed UUID/Beast/DF17/18/MLAT compatibility checks")


class VersionStore:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.state_path = directory / "state.json"
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.state = state if isinstance(state, dict) else {}
        except (OSError, ValueError):
            self.state = {}

    def save_state(self):
        temporary = self.state_path.with_suffix(".new")
        temporary.write_text(json.dumps(self.state, sort_keys=True), encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, self.state_path)

    def save(self, candidate: Candidate):
        path = self.directory / (candidate.release_id + ".py")
        if not path.exists() or path.read_bytes() != candidate.code:
            temporary = path.with_suffix(".new")
            temporary.write_bytes(candidate.code)
            temporary.chmod(0o600)
            os.replace(temporary, path)
        self.state.setdefault("versions", {})[candidate.release_id] = {
            "feed_host": candidate.feed_host, "feed_port": candidate.feed_port,
            "script_sha256": candidate.script_sha256}

    def load(self, digest: str | None) -> Candidate | None:
        if not isinstance(digest, str) or not HASH.fullmatch(digest):
            return None
        try:
            info = self.state.get("versions", {})[digest]
            candidate = identify((self.directory / (digest + ".py")).read_bytes(),
                                 info["feed_host"], int(info["feed_port"]), info.get("script_sha256", ""))
            if candidate.release_id != digest:
                return None
            validate(candidate)
            return candidate
        except (OSError, ValueError, KeyError, TypeError, UpdateError):
            return None

    def working(self) -> Candidate:
        for key in ("active", "previous"):
            candidate = self.load(self.state.get(key))
            if candidate:
                if key != "active":
                    self.state["active"] = candidate.release_id
                    self.save_state()
                return candidate
        candidate = identify(BUNDLED.read_bytes())
        validate(candidate)
        self.save(candidate)
        self.state["active"] = candidate.release_id
        self.save_state()
        return candidate

    def activate(self, candidate: Candidate):
        self.save(candidate)
        old = self.state.get("active")
        if old != candidate.release_id:
            self.state["previous"] = old
        self.state["active"] = candidate.release_id
        self.state.pop("rejected", None)
        self.save_state()

    def reject(self, candidate: Candidate):
        self.state["rejected"] = candidate.release_id
        self.save_state()

    def check(self) -> Candidate | None:
        headers = {"User-Agent": "AeroNexus-HA/1.1.0", "Accept": "text/plain"}
        # Conditional GET is only used when a validated cached version exists.
        cached_latest = self.state.get("latest") or self.state.get("active")
        if cached_latest and self.load(cached_latest):
            if self.state.get("etag"):
                headers["If-None-Match"] = self.state["etag"]
            if self.state.get("last_modified"):
                headers["If-Modified-Since"] = self.state["last_modified"]
        req = Request(SOURCE_URL, headers=headers)
        try:
            opener = build_opener(ProxyHandler({}), OfficialOriginOnly())
            with opener.open(req, timeout=TIMEOUT) as response:
                data = response.read(MAX_SCRIPT + 1)
                etag, modified = response.headers.get("ETag"), response.headers.get("Last-Modified")
        except HTTPError as exc:
            if exc.code == 304:
                self.state["checked_at"] = datetime.now(timezone.utc).isoformat()
                self.save_state()
                LOG.info("Official upstream check: unchanged (HTTP 304)")
                latest = self.state.get("latest")
                if latest != self.state.get("active") and latest != self.state.get("rejected"):
                    return self.load(latest)
                return None
            raise UpdateError(f"Official download returned HTTP {exc.code}") from None
        except (OSError, ValueError) as exc:
            raise UpdateError(f"Official download failed ({type(exc).__name__})") from None
        candidate = extract(data)
        if candidate.release_id == self.state.get("rejected"):
            LOG.warning("Latest upstream previously failed at runtime; keeping the working version (%s)", candidate.sha256[:12])
            return None
        validate(candidate)
        self.save(candidate)
        self.state.update(etag=etag, last_modified=modified,
                          checked_at=datetime.now(timezone.utc).isoformat(),
                          latest=candidate.release_id, script_sha256=candidate.script_sha256)
        self.save_state()
        LOG.info("Official upstream checked: relay=%s script=%s", candidate.sha256[:12], candidate.script_sha256[:12])
        return candidate
