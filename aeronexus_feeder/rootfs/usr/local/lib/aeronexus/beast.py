"""Beast framing adapted from the Python relay embedded in the supplied feed.sh.

Preserves UUID 0xE4, DF17/18 filtering, MLAT exclusion and Beast byte escaping.
See NOTICE.md for provenance. The E3 receiver-id path validates escapes here.
"""
BUF_MAX = 1 << 16
HB = b'\x1a\x31' + b'\x00' * 9
PLEN = {0x31: 2, 0x32: 7, 0x33: 14}
MLAT_TS = b'\xff\x00MLAT'


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
                        if buf[k + 1] != 0x1a:
                            break  # A new frame begins; resume at its marker.
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

