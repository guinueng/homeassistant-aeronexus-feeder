#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AeroNexus ADS-B 피더 — 파이썬 중계기 (feed.sh 가 설치한다 · 2026-09-13 신설)

무엇을 하나
    기존 수신기의 Beast 출력(BEAST_HOST:BEAST_PORT, 보통 127.0.0.1:30005)을 읽어
    AeroNexus(FEED_HOST:FEED_PORT)로 보낸다. 접속하자마자 UUID 프레임(0x1a 0xE4 + 36자)을
    한 번 보내 «누구인가»를 밝히고, 그 뒤로 Beast 프레임을 그대로 흘려보낸다.
    readsb 의 beast_reduce_plus_out 이 하는 일과 같은 모양이라 서버는 둘을 구분하지 않는다.

왜 있나
    PiAware·FR24 Pi24·RadarBox 이미지에는 readsb 가 없다. 그렇다고 남의 기계에 컴파일러를
    돌리거나 패키지를 깔지 않는다 — python3 표준 라이브러리만 쓴다(라즈베리파이 OS 기본).

무엇을 거르나 (FILTER)
    adsb(기본) : Mode-S 긴 프레임(0x33) 중 DF17·18(ADS-B)만 보낸다. 서버가 해석하는 것이
                 그 둘뿐이라 잃는 것이 없고, 대역폭은 전체 Beast 의 절반 아래로 준다.
    all        : 전부 보낸다(진단용).

하지 않는 것
    · 파일을 쓰지 않는다(systemd 가 ProtectSystem=strict 로 막아 둔다). 기록은 stderr → journal.
    · 포트를 열지 않는다. 수신기 쪽·서버 쪽 모두 «나가는» 연결이다.
    · 해석하지 않는다 — 좌표·고도를 풀지 않고 바이트를 옮길 뿐이다(판정은 서버 한 곳).
    · 서버가 끊으면(UUID 미등록·꺼짐) 물러나며 다시 붙는다(2초 → 최대 60초).
      ⚠ 지도 공개 승인 전에는 끊지 않는다 — 서버는 받되 공개 지도에만 싣지 않는다(2026-09-14).

설정은 환경변수(/etc/default/aeronexus-feed): UUID BEAST_HOST BEAST_PORT FEED_HOST FEED_PORT FILTER
python 3.5 이상이면 된다 — f-string 등 새 문법을 일부러 쓰지 않았다(옛 이미지 대비).
"""
import os
import select
import socket
import sys
import time

UUID = os.environ.get('UUID', '').strip()
BEAST_HOST = os.environ.get('BEAST_HOST', '127.0.0.1').strip()
BEAST_PORT = int(os.environ.get('BEAST_PORT', '30005'))
FEED_HOST = os.environ.get('FEED_HOST', 'aeronexus.kr').strip()
FEED_PORT = int(os.environ.get('FEED_PORT', '30004'))
FILTER = os.environ.get('FILTER', 'adsb').strip().lower()

HEARTBEAT_S = 30.0          # 이만큼 조용하면 Beast 심장박동(수신기·readsb 가 쓰는 것과 같은 모양)을 보낸다
STAT_S = 300.0              # 통계 한 줄 주기
BACKOFF_MIN, BACKOFF_MAX = 2.0, 60.0
STABLE_S = 60.0             # 이만큼 붙어 있었으면 다음 재접속 간격을 처음(2초)으로 되돌린다
BUF_MAX = 1 << 16
HB = b'\x1a\x31' + b'\x00' * 9          # 0x31 + ts6 + sig1 + payload2, 전부 0 = Beast 심장박동
PLEN = {0x31: 2, 0x32: 7, 0x33: 14}     # Mode-A/C · Mode-S 짧은 · Mode-S 긴
# 2026-10-25 — dump1090-fa·readsb 가 MLAT 결과에 찍는 타임스탬프 표식(MAGIC_MLAT_TIMESTAMP 0xFF004D4C4154).
#   수신기가 --forward-mlat 으로 내보내도 이 표식이 있으면 버린다.
MLAT_TS = b'\xff\x00MLAT'
FAQ_URL = 'https://aeronexus.kr/feeder-faq.html'


def log(msg):
    # ⚠ 바이트로 쓴다 — systemd 아래 C 로케일의 python 3.5/3.6 은 한글 str 을 stderr 에 쓰다 죽는다
    data = (msg + '\n').encode('utf-8', 'replace')
    try:
        sys.stderr.buffer.write(data)
    except Exception:
        sys.stderr.write(data.decode('ascii', 'replace'))
    sys.stderr.flush()


def uuid_frame(u):
    """readsb sendUUID() 와 같은 모양 — 항상 36바이트, 모자라면 'f' 로 채운다."""
    b = u.encode('ascii', 'ignore')[:36]
    return b'\x1a\xe4' + b + b'f' * (36 - len(b))


class Splitter(object):
    """Beast 바이트열을 프레임 단위로 잘라 거른다. 잘린 조각은 다음 chunk 와 이어 붙인다.

    Beast 규칙: 프레임 = 0x1a, 종류 1바이트, 타임스탬프 6, 신호세기 1, 페이로드(종류별 2/7/14).
    페이로드 안의 0x1a 는 0x1a 0x1a 로 이스케이프된다 — 그래서 «0x1a 뒤에 0x1a 가 아닌 바이트»만이
    프레임의 시작이다. 이 성질로 어디서 시작해도 동기를 다시 잡는다.
    """

    def __init__(self, mode):
        self.buf = b''
        self.mode = mode
        self.n_in = 0
        self.n_out = 0
        self.n_resync = 0
        self.n_mlat = 0
        self.df = {}

    def want(self, typ, df):
        if self.mode == 'all':
            return True
        return typ == 0x33 and df in (17, 18)

    def feed(self, chunk):
        buf = self.buf + chunk
        out = bytearray()
        n = len(buf)
        i = 0
        while True:
            j = buf.find(b'\x1a', i)
            if j < 0:
                i = n
                break
            if j + 1 >= n:
                i = j
                break
            t = buf[j + 1]
            if t == 0x1a:                      # 프레임 한가운데(이스케이프) — 동기가 맞을 때까지 넘긴다
                i = j + 2
                self.n_resync += 1
                continue
            if t == 0xE4:                      # 상대의 UUID 프레임(36바이트, 이스케이프 없음) — 우리 것을 보내므로 버린다
                if j + 38 > n:
                    i = j
                    break
                i = j + 38
                continue
            if t == 0xE3:                      # 수신기 id 8바이트(이스케이프 있음) — 버린다
                k = j + 2
                c = 0
                short = False
                while c < 8:
                    if k >= n:
                        short = True
                        break
                    if buf[k] == 0x1a:
                        if k + 1 >= n:
                            short = True
                            break
                        k += 2
                    else:
                        k += 1
                    c += 1
                if short:
                    i = j
                    break
                i = k
                continue
            plen = PLEN.get(t)
            if plen is None:                   # 모르는 종류 — 한 바이트 넘기고 다시 찾는다
                i = j + 1
                self.n_resync += 1
                continue
            need = 7 + plen
            k = j + 2
            c = 0
            short = False
            broken = False
            first = -1
            ts = bytearray()
            while c < need:
                if k >= n:
                    short = True
                    break
                b = buf[k]
                if b == 0x1a:
                    if k + 1 >= n:
                        short = True
                        break
                    if buf[k + 1] != 0x1a:     # 새 프레임이 시작됐다 — 이 프레임은 잘린 것
                        broken = True
                        break
                    k += 2
                else:
                    k += 1
                if c < 6:
                    ts.append(b)               # 타임스탬프(이스케이프 푼 값)
                if c == 7:
                    first = b                  # 페이로드 첫 바이트 → DF
                c += 1
            if short:
                i = j
                break
            if broken:
                i = k
                self.n_resync += 1
                continue
            self.n_in += 1
            if ts == MLAT_TS:                  # MLAT 결과 — 다른 회사가 계산한 위치라 어떤 모드에서도 보내지 않는다
                self.n_mlat += 1
                i = k
                continue
            df = ((first >> 3) & 0x1f) if (t != 0x31 and first >= 0) else -1
            if t == 0x33:
                self.df[df] = self.df.get(df, 0) + 1
            if self.want(t, df):
                out += buf[j:k]
                self.n_out += 1
            i = k
        rest = buf[i:]
        if len(rest) > BUF_MAX:                # 0x1a 가 한 번도 안 오는 쓰레기 — 끝만 남긴다
            rest = rest[-4096:]
            self.n_resync += 1
        self.buf = rest
        return bytes(out)


def connect(host, port, timeout):
    s = socket.create_connection((host, port), timeout=timeout)
    s.settimeout(None)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    try:
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        pass
    return s


def close(s):
    try:
        s.close()
    except Exception:
        pass


def main():
    if len(UUID) < 32:
        log('UUID 가 없거나 짧습니다: %r' % UUID)
        return 2
    if FILTER not in ('adsb', 'all'):
        log('FILTER 는 adsb|all 이어야 합니다: %r' % FILTER)
        return 2
    log('AeroNexus 피더 중계기 시작 — %s:%d → %s:%d (uuid %s… · filter=%s)'
        % (BEAST_HOST, BEAST_PORT, FEED_HOST, FEED_PORT, UUID[:8], FILTER))
    src = None
    up = None
    src_next = 0.0
    up_next = 0.0
    src_back = BACKOFF_MIN
    up_back = BACKOFF_MIN
    up_since = 0.0
    now = time.time()
    last_tx = now
    last_stat = now
    tx_bytes = 0
    sp = Splitter(FILTER)
    src_hinted = False

    def drop_up(why):
        nonlocal up, up_next, up_back
        close(up)
        up = None
        if now - up_since >= STABLE_S:
            up_back = BACKOFF_MIN
        else:
            up_back = min(up_back * 2, BACKOFF_MAX)
        up_next = now + up_back
        log('%s — %.0f초 뒤 다시 붙습니다' % (why, up_back))

    while True:
        now = time.time()
        if up is None and now >= up_next:
            try:
                up = connect(FEED_HOST, FEED_PORT, 10.0)
                up.sendall(uuid_frame(UUID))
                up_since = now
                last_tx = now
                log('AeroNexus 연결됨 %s:%d' % (FEED_HOST, FEED_PORT))
            except Exception as e:
                up = None
                up_next = now + up_back
                log('AeroNexus 연결 실패 (%s) — %.0f초 뒤 재시도' % (e, up_back))
                up_back = min(up_back * 2, BACKOFF_MAX)
        if src is None and now >= src_next:
            try:
                src = connect(BEAST_HOST, BEAST_PORT, 5.0)
                src_back = BACKOFF_MIN
                sp.buf = b''
                log('수신기 Beast 연결됨 %s:%d' % (BEAST_HOST, BEAST_PORT))
            except Exception as e:
                src = None
                src_next = now + src_back
                log('수신기 Beast 연결 실패 (%s) — %.0f초 뒤 재시도 (수신기가 뜨면 저절로 붙습니다)'
                    % (e, src_back))
                src_back = min(src_back * 2, BACKOFF_MAX)
                if not src_hinted and isinstance(e, ConnectionRefusedError):
                    src_hinted = True          # 한 번만 — 포트가 닫혀 있다는 뜻이다
                    log('  → %s:%d 에서 자료를 내보내는 프로그램이 없습니다. FR24 Pi24 라면 설정(:8754)의 '
                        'Process arguments 에 --net 을 넣어야 열립니다 — 설치 명령을 다시 실행하면 대신 켜 드립니다. %s'
                        % (BEAST_HOST, BEAST_PORT, FAQ_URL))

        rl = [s for s in (src, up) if s is not None]
        if not rl:
            time.sleep(1.0)
            continue
        try:
            r, _, _ = select.select(rl, [], [], 1.0)
        except Exception as e:
            log('select 오류 (%s)' % e)
            time.sleep(1.0)
            r = []
        now = time.time()

        if src is not None and src in r:
            try:
                chunk = src.recv(65536)
            except Exception as e:
                chunk = b''
                log('수신기 읽기 오류: %s' % e)
            if not chunk:
                close(src)
                src = None
                src_next = now + src_back
                log('수신기 연결 끊김 — %.0f초 뒤 다시 붙습니다' % src_back)
            else:
                out = sp.feed(chunk)
                if out and up is not None:
                    try:
                        up.sendall(out)
                        tx_bytes += len(out)
                        last_tx = now
                    except Exception as e:
                        drop_up('AeroNexus 보내기 실패 (%s)' % e)

        if up is not None and up in r:
            try:
                d = up.recv(4096)
            except Exception:
                d = b''
            if not d:
                drop_up('AeroNexus 쪽이 연결을 끊었습니다 (UUID가 등록되지 않았거나, 관리자가 꺼 두었거나, '
                        '같은 UUID가 다른 곳에서 이미 접속해 있을 수 있습니다)')

        if up is not None and now - last_tx >= HEARTBEAT_S:
            try:
                up.sendall(HB)
                last_tx = now
            except Exception as e:
                drop_up('심장박동 보내기 실패 (%s)' % e)

        if now - last_stat >= STAT_S:
            last_stat = now
            log('통계 %d분: 프레임 받음 %d · 보냄 %d · 보낸 바이트 %d · 재동기 %d · MLAT 버림 %d · DF %s'
                % (int(STAT_S // 60), sp.n_in, sp.n_out, tx_bytes, sp.n_resync, sp.n_mlat, sorted(sp.df.items())))
            sp.n_in = sp.n_out = sp.n_resync = sp.n_mlat = 0
            sp.df = {}
            tx_bytes = 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
