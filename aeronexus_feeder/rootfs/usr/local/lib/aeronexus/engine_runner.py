#!/usr/bin/env python3
"""Run the official embedded relay in a separate, unprivileged Python process."""
import json
import os
import socket
import sys
import threading
import time

MAX_CODE = 512 * 1024
UUID_WARNING_PREFIX = "[HA UUID warning] "
EARLY_DISCONNECT_S = 10.0
UUID_WARNING_COOLDOWN_S = 60.0
UUID_IN_USE_HINT = (
    "UUID가 다른 곳에서 사용 중일 수 있습니다. UUID 하나는 기기 하나에서만 사용하세요. "
    "라즈베리파이에서 HA로 옮겼다면 파이 쪽 AeroNexus 피더를 먼저 제거하세요 "
    "(기존 설치 명령 끝에 --uninstall). UUID 등록/활성화 상태와 네트워크도 확인하세요. "
    "https://aeronexus.kr/feeder-faq.html"
)


class DisconnectHints:
    """Observe early remote closes without changing official relay source or traffic."""
    def __init__(self, log, clock=None):
        self.log = log
        self.clock = clock or time.monotonic
        self.last_notice = None

    def report(self, connected_at):
        now = self.clock()
        if not 0 <= now - connected_at <= EARLY_DISCONNECT_S:
            return
        if self.last_notice is not None and now - self.last_notice < UUID_WARNING_COOLDOWN_S:
            return
        self.last_notice = now
        try:
            self.log(UUID_WARNING_PREFIX + UUID_IN_USE_HINT)
        except Exception:
            # Diagnostics must not change socket results or the relay's reconnect loop.
            pass


class ObservedFeedSocket:
    """Pass socket operations through; report remote EOF/reset during initial setup."""
    def __init__(self, sock, hints):
        self.sock = sock
        self.hints = hints
        self.connected_at = hints.clock()
        self.closed = False
        self.reported = False

    def __getattr__(self, name):
        return getattr(self.sock, name)

    def remote_closed(self):
        if not self.closed and not self.reported:
            self.reported = True
            self.hints.report(self.connected_at)

    def recv(self, *args, **kwargs):
        try:
            data = self.sock.recv(*args, **kwargs)
        except (ConnectionResetError, ConnectionAbortedError):
            self.remote_closed()
            raise
        if data == b"":
            self.remote_closed()
        return data

    def sendall(self, *args, **kwargs):
        try:
            return self.sock.sendall(*args, **kwargs)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.remote_closed()
            raise

    def close(self):
        self.closed = True
        return self.sock.close()


def runtime_connect(connect, feed_host, feed_port, hints):
    """Keep the existing timeout policy; observe only the AeroNexus destination."""
    def bounded_connect(host, port, *args, **kwargs):
        sock = connect(host, port, *args, **kwargs)
        sock.settimeout(5.0)
        if (host, port) == (feed_host, feed_port):
            return ObservedFeedSocket(sock, hints)
        return sock
    return bounded_connect


def limits():
    if os.name == "posix":
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
        if sys.argv[1] == "--validate":
            resource.setrlimit(resource.RLIMIT_CPU, (5, 5))


def packet(df=17, timestamp=b"\x01\x02\x03\x04\x05\x06"):
    body = timestamp + b"\x1a" + bytes([df << 3]) + bytes(range(1, 13)) + b"\x1a"
    return b"\x1a\x33" + body.replace(b"\x1a", b"\x1a\x1a")


def check(namespace):
    uuid = "12345678-1234-4321-8765-123456789abc"
    assert namespace["uuid_frame"](uuid) == b"\x1a\xe4" + uuid.encode("ascii")
    splitter = namespace["Splitter"]
    a, b, other = packet(17), packet(18), packet(11)
    mlat = packet(17, b"\xff\x00MLAT")
    expected = a + b
    data = a + other + mlat + b
    for boundary in range(len(data) + 1):
        sp = splitter("adsb")
        assert sp.feed(data[:boundary]) + sp.feed(data[boundary:]) == expected
    sp = splitter("all")
    assert sp.feed(a + mlat + other) == a + other
    sp = splitter("adsb")
    assert sp.feed(b"\x1a\xe4" + uuid.encode("ascii") + a) == a
    assert callable(namespace["main"])
    check_main(namespace)


def check_main(namespace):
    """Exercise the actual upstream main loop using socket pairs only.

    The candidate never receives real network endpoints during this probe.
    """
    source, source_peer = socket.socketpair()
    destination, destination_peer = socket.socketpair()
    destination_peer.settimeout(2)
    stopped = threading.Event()
    failures = []

    class EndProbe(BaseException):
        pass

    real_select = namespace["select"]
    class ProbeSelect:
        @staticmethod
        def select(read, write, error, timeout=None):
            if stopped.is_set():
                raise EndProbe()
            return real_select.select(read, write, error, .05)

    def fake_connect(host, port, *args, **kwargs):
        if stopped.is_set(): raise EndProbe()
        if (host, port) == (namespace["FEED_HOST"], namespace["FEED_PORT"]): return destination
        if (host, port) == (namespace["BEAST_HOST"], namespace["BEAST_PORT"]): return source
        raise AssertionError("Unexpected relay connection")

    namespace["select"] = ProbeSelect
    namespace["connect"] = fake_connect
    namespace["log"] = lambda *_: None

    def run():
        try:
            namespace["main"]()
        except EndProbe:
            pass
        except BaseException as exc:
            failures.append(type(exc).__name__)

    thread = threading.Thread(target=run, daemon=True)
    try:
        expected = b"\x1a\xe4" + namespace["UUID"].encode("ascii") + packet(17) + packet(18)
        source_peer.sendall(packet(11) + packet(17, b"\xff\x00MLAT") + packet(17) + packet(18))
        thread.start()
        received = b""
        while len(received) < len(expected):
            chunk = destination_peer.recv(len(expected) - len(received))
            if not chunk: break
            received += chunk
        assert received == expected
    finally:
        stopped.set()
        if thread.ident is not None: thread.join(timeout=1)
        for sock in (source, source_peer, destination, destination_peer): sock.close()
    assert not thread.is_alive() and not failures


def main():
    limits()
    data = sys.stdin.buffer.read(MAX_CODE + 1)
    if not data or len(data) > MAX_CODE:
        raise ValueError("Invalid relay source size")
    namespace = {"__name__": "aeronexus_candidate", "__file__": "<official-aeronexus-relay>"}
    exec(compile(data, "<official-aeronexus-relay>", "exec"), namespace)
    if sys.argv[1] == "--validate":
        check(namespace)
        print(json.dumps({"aeronexus_validation": "ok"}), flush=True)
    else:
        namespace["STAT_S"] = float(os.environ.get("AERO_STAT_S", "60"))
        original_connect = namespace.get("connect")
        if callable(original_connect):
            hints = DisconnectHints(namespace["log"])
            namespace["connect"] = runtime_connect(
                original_connect, namespace["FEED_HOST"], namespace["FEED_PORT"], hints)
        sys.exit(namespace["main"]())


if __name__ == "__main__":
    main()
