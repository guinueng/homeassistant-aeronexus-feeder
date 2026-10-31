# AeroNexus Feeder 설치 가이드

확인일: **2026-10-31 (한국 시간)** · 앱 버전: **1.0.0**

## 1. 준비와 기본 동작

Home Assistant OS와 정상 수신 중인 ADS-B Multi-Portal Feeder가 필요합니다.
지원 CPU는 `aarch64`와 `amd64`입니다. 오래된 32비트 HAOS용 이미지는 제공하지 않습니다.
새 앱은 설치할 때 인터넷에서 공식 base 이미지와 Python 패키지를 내려받아 빌드합니다.

일반적인 설치에서는 새 앱에 **UUID만** 입력합니다. UUID를 아직 받지 못했어도 설치할 수 있습니다.
기존 피더 한 개가 표준 slug `adsb-multi-portal-feeder`로 설치되어 있고 내부 Beast 출력이
열려 있다는 조건입니다. 기존 피더가 꺼져 있으면 새 앱은 기다렸다가 다시 연결합니다.

```text
기존 ADS-B 앱 컨테이너
  USB/SDR → dump1090 → Beast TCP 30005
                         ↑ 새 앱이 읽는 연결
                         │ Home Assistant 내부 네트워크
새 AeroNexus 앱 컨테이너
  UUID 설정 → 필터/중계 ─────→ aeronexus.kr:30004
                             UUID 프레임 → Beast DF17/18
```

Beast 서버와 AeroNexus 서버 양쪽으로 새 앱이 TCP 연결을 시작합니다.
공유기 포트포워딩은 필요 없습니다. 기존 피더의 FR24/FlightAware 설정과 USB 장치는
그대로 사용합니다. 이 앱은 새 디코더나 systemd 서비스를 설치하지 않습니다.

## 2. 경로를 먼저 구분하기

같은 `/config`, `/data`, `/`라는 이름도 **어느 컨테이너에서 보는지**에 따라 다른 폴더입니다.
`~`는 현재 셸의 홈 디렉터리이며 로컬 앱 폴더라는 보장이 없습니다.

| 보는 위치 | 경로 | 의미 |
|---|---|---|
| Windows Samba 공유 | `\\homeassistant.local\local_apps\aeronexus_feeder` | 로컬 앱 소스 복사 위치 |
| 최신 공식 Terminal & SSH 내부 | `/local_apps/aeronexus_feeder` | 위 공유와 같은 소스 폴더 |
| 예전 Terminal 앱 내부 | `/addons/aeronexus_feeder` | 구형 `addons` 매핑을 사용하는 경우의 같은 용도 |
| Terminal / File editor | `/homeassistant` (구형 매핑은 `/config`) | Home Assistant Core 설정; 앱 설치 위치가 아님 |
| Supervisor 컨테이너, 최신 upstream | `/data/apps/local/aeronexus_feeder` | Supervisor가 보는 로컬 소스 내부 경로 |
| HAOS 호스트, 최신 upstream | `${SUPERVISOR_SHARE}/apps/local/aeronexus_feeder` | Supervisor 공유 루트 아래의 실제 소스 |
| 새 AeroNexus 컨테이너 | `/usr/local/lib/aeronexus/` | 빌드 때 이미지에 복사한 실행 코드 |
| 새 AeroNexus 컨테이너 | `/data/options.json` | Supervisor가 시작 전에 쓰는 UUID 등 사용자 옵션 |
| 새 AeroNexus 컨테이너 | `/data` | 이 앱만의 영구 데이터/백업 대상 |

최신 Supervisor 코드의 저장 구조는 `apps/local`, `apps/data`, `app_configs`입니다.
예전 버전은 `addons/local`, `addons/data`, `addon_configs`를 사용했습니다.
**호스트의 절대 경로는 설치된 Supervisor와 `SUPERVISOR_SHARE` 값에 따라 확인해야 합니다.**
일반 HAOS의 공유 루트로 알려진 `/mnt/data/supervisor`를 무조건 조합해 직접 편집하지 말고,
공식 Terminal & SSH의 `/local_apps` 또는 Samba 공유로 설치하세요.
위 표의 upstream 경로는 사용자 장비에서 실측한 값이 아닙니다. [공식 경로 코드](https://github.com/home-assistant/supervisor/blob/main/supervisor/config.py)를 기준으로 구분했습니다.

`/app_configs/local_aeronexus_feeder` 같은 공개 앱 설정 폴더도 **소스 설치 위치가 아닙니다.**
이 앱은 `app_config`나 `homeassistant_config`를 매핑할 필요가 없어 요청하지 않습니다.
UUID는 구성 UI로 입력합니다.

## 3. 권장 설치: Windows 탐색기와 Samba

1. Home Assistant에서 **설정 → 앱 → 앱 설치**로 들어가 공식 **Samba share**를 설치합니다.
2. Samba의 계정을 설정하고 시작합니다. 최신 버전의 `enabled_shares`에 `local_apps`가
   포함되어 있어야 합니다. 이미 접속 중이면 로그아웃/재접속이 필요할 수 있습니다.
3. Windows 탐색기 주소창에 `\\homeassistant.local\local_apps`를 입력합니다.
   이름으로 연결되지 않으면 `\\HA_IP\local_apps`를 사용합니다.
4. ZIP을 PC에서 압축 해제합니다. 안의 **`aeronexus_feeder` 폴더 전체**를 공유에 복사합니다.
5. 다음처럼 파일이 **한 단계 바로 아래**에 있는지 확인합니다.

```text
local_apps/
└── aeronexus_feeder/
    ├── config.yaml
    ├── Dockerfile
    ├── rootfs/
    ├── translations/
    ├── DOCS.md
    └── ...
```

`local_apps/aeronexus_feeder/aeronexus_feeder/config.yaml`처럼 이중 폴더가 생기면 수정하세요.
`config.yaml.txt`처럼 숨겨진 확장자가 붙지 않아야 합니다.
이 압축 파일은 **앱 소스 ZIP**입니다. Home Assistant 백업 복원 화면에 올리는 파일이 아닙니다.

## 4. Terminal & SSH로 설치하기

공식 **Terminal & SSH** 앱의 웹 터미널에서 작업합니다. HAOS 호스트 콘솔이나
Home Assistant Core 컨테이너의 셸과 구분하세요. 보호 모드를 해제할 필요는 없습니다.

먼저 실제 공유 매핑을 확인합니다.

```sh
pwd
ls -ld /local_apps /addons /homeassistant /config /share 2>/dev/null
awk '$5 == "/local_apps" || $5 == "/addons" {print}' /proc/self/mountinfo
```

최신 공식 앱에서는 `/local_apps`를 사용합니다. 이 경로가 없다면 Terminal 앱을 업데이트하거나,
그 앱에 실제로 매핑된 구형 `/addons`를 확인하세요. **매핑도 없는 `/local_apps`를 임의로 만들면
Terminal 컨테이너 안에만 폴더가 생길 수 있습니다.** `~/local_apps`도 같은지 확인 없이 사용하지 마세요.

이미 소스를 File editor를 이용해 `/homeassistant/aeronexus_feeder`에 저장했다면,
**아직 대상 폴더가 없는 첫 설치**에서 다음을 실행할 수 있습니다.

```sh
test -d /local_apps || { echo 'local_apps 공유가 없습니다. Terminal 앱 매핑을 확인하세요.'; exit 1; }
test -f /homeassistant/aeronexus_feeder/config.yaml || { echo '원본 소스 위치를 확인하세요.'; exit 1; }
test ! -e /local_apps/aeronexus_feeder || { echo '대상 폴더가 이미 있습니다. 먼저 별도 백업하세요.'; exit 1; }
mkdir -p /local_apps/aeronexus_feeder
cp -a /homeassistant/aeronexus_feeder/. /local_apps/aeronexus_feeder/
ls -l /local_apps/aeronexus_feeder/config.yaml /local_apps/aeronexus_feeder/Dockerfile
```

현재 File editor에서 보이는 홈이 `/config`인 경우에는 위의 **원본 경로만** 실제 위치로 바꿉니다.
기존 앱이 실제 `/addons` 매핑을 쓴다면 **대상 경로만** `/addons/aeronexus_feeder`로 바꿉니다.
복사가 끝나면 Supervisor에서 앱을 찾는지 확인한 뒤 staging 소스를 정리하면 됩니다.

ZIP을 Samba `share` 공유에 올렸고 터미널에 `unzip`이 있는 경우에는 다음 첫 설치 방법도 가능합니다.

```sh
test -d /local_apps || { echo 'local_apps 공유 매핑을 확인하세요.'; exit 1; }
test ! -e /local_apps/aeronexus_feeder || { echo '이미 있는 소스를 먼저 백업하세요.'; exit 1; }
unzip /share/aeronexus_feeder-1.0.0.zip -d /local_apps
```

`unzip`이 없으면 PC에서 압축을 풀고 Samba로 복사하는 방법을 사용하세요.

## 5. File editor에서 루트 권한이 필요한가?

**이 작업에는 File editor의 루트 접근이나 보호 모드 해제가 필요하지 않습니다.**
공식 File editor의 현재 설정은 Home Assistant 설정 폴더와 공개 앱 설정 등은 매핑하지만,
`local_apps`는 매핑하지 않습니다. `enforce_basepath`를 꺼도 **없는 마운트가 새로 생기지 않습니다.**
File editor에서 보이는 `/`는 File editor 컨테이너의 루트이며 HAOS 호스트 루트가 아닙니다.
따라서 소스 편집은 Samba 또는 `/local_apps`가 매핑된 Terminal & SSH로 하세요.
이 구분은 [공식 File editor 설정](https://github.com/home-assistant/addons/blob/master/configurator/config.yaml)과
[Terminal & SSH 설정](https://github.com/home-assistant/addons/blob/master/ssh/config.yaml)에서 확인했습니다.

## 6. 앱 검색·설치·UUID 입력

1. **설정(Settings) → 앱(Apps) → 앱 설치(Install app)**로 앱 스토어를 엽니다.
2. 오른쪽 위 **⋮ → 업데이트 확인(Check for updates)**을 실행합니다. 필요하면 브라우저를 새로 고칩니다.
3. **로컬 앱(Local apps)**에서 **AeroNexus Feeder**를 선택하고 **설치(Install)**합니다.
4. **구성(Configuration)** 탭에는 기본으로 **AeroNexus UUID**만 나옵니다.
5. AeroNexus가 발급한 UUID를 입력하고 **저장(Save)**합니다.
6. **시작(Start)**합니다. 이미 실행 중이었다면 재시작 안내를 수락하거나 **재시작(Restart)**합니다.
7. **정보(Info)**에서 **부팅 시 시작(Start on boot)**과 **Watchdog**을 켭니다.
8. **로그(Log)**에서 연결과 실제 전송량을 확인합니다.

이 UI 동작은 [공식 옵션 문서](https://contributors.home-assistant.io/apps/guides/options/)와
[현재 Frontend 설정 화면 코드](https://github.com/home-assistant/frontend/blob/dev/src/panels/config/apps/app-view/config/supervisor-app-config.ts)를 확인했습니다.
설치된 Frontend가 오래되었으면 ‘애드온’, ‘애드온 스토어’ 등 구형 이름일 수 있습니다.

UUID를 나중에 넣을 때는 빈 상태로 설치/시작해도 됩니다. 로그에
`UUID is empty. Waiting without network connections`가 나오며 아무 서버에도 연결하지 않습니다.
나중에 UUID를 입력하고 **저장 → 재시작**하세요. 설정을 저장하는 것만으로 실행 중 프로세스가 바뀌지 않습니다.

선택 옵션을 쓰려면 **사용하지 않는 선택 옵션 표시**를 켜거나 **⋮ → YAML로 편집(Edit in YAML)**합니다.
기본 구성의 YAML 예시는 다음과 같습니다. 예시 UUID 대신 발급받은 값을 넣습니다.

```yaml
uuid: "12345678-1234-4321-8765-123456789abc"
```

직접 주소가 필요한 경우에만 추가합니다.

```yaml
uuid: "12345678-1234-4321-8765-123456789abc"
beast_host: "f1c878cb-adsb-multi-portal-feeder"
beast_port: 30005
filter: adsb
stats_interval: 60
```

`f1c878cb-...`는 표준 MaxWinterstein 저장소의 예입니다. 다른 저장소/로컬 설치에서는
다른 접두사가 붙습니다. 기존 피더의 앱 URL/`ha addons list`로 실제 ID를 확인하고,
ID의 `_`를 `-`로 바꾸면 내부 DNS 이름이 됩니다. `addon_` 컨테이너 이름을 그대로 쓰지 않습니다.

## 7. 네트워크 설정 — 30005와 30004를 구분하기

| 구간 | 새 앱이 연결하는 주소 | 호스트 포트 공개 |
|---|---|---|
| 기본: 기존 피더 내부 출력 | `<기존 앱 ID에서 _를 -로 치환>:30005` | 필요 없음 |
| 선택: LAN에 공개한 수신기 | `수신기_LAN_IP:실제_공개_포트` | 수신기 쪽에서만 필요할 수 있음 |
| AeroNexus 송신 | `aeronexus.kr:30004` | 새 앱/공유기에 수신 포트 개방 불필요 |

새 앱은 `host_network: false`입니다. 여기서 `127.0.0.1:30005`는 새 앱 자신의 포트이므로,
다른 컨테이너인 기존 피더를 읽지 못합니다. 터미널에서 `localhost`로 성공했다고 해서
새 앱에서도 같은 주소가 맞는 것은 아닙니다. 앱마다 네트워크 네임스페이스가 다릅니다.

기존 피더 `config.yaml`의 `30005/tcp: null`은 **호스트 공개가 꺼짐**이라는 뜻입니다.
컨테이너 내부의 30005 서비스 자체가 꺼졌다는 뜻은 아닙니다.
기본 구성에서는 기존 앱의 Network 항목을 변경하지 않습니다.
기존 피더의 `30004`는 **Beast 입력**이고, 우리가 읽을 곳은 **Beast 출력 30005**입니다.
이는 [기존 앱 설정](https://github.com/MaxWinterstein/homeassistant-addons/blob/main/adsb-multi-portal-feeder/config.yaml)에 명시되어 있습니다.

기존 피더는 보통 `SERVICE_ENABLE_DUMP1090: true`이고, upstream 실행 스크립트가 `--net`을 붙입니다.
커스텀 `DUMP1090_ADDITIONAL_ARGS`로 네트워크 출력/바인딩을 바꿨거나 외부 수신기를 쓰면
실제 Beast 출력을 확인해야 합니다. 내부 연결도 서버가 접근 가능한 인터페이스에 리슨해야 성립합니다.
`0.0.0.0`은 서버 리슨 주소이며 `beast_host`에 넣을 대상 주소가 아닙니다.

자동 탐색은 `GET /supervisor/info` 응답의 설치 앱 목록에서 표준 slug를 하나 선택합니다.
필요 권한은 `hassio_api: true`, `hassio_role: default`입니다.
`GET /addons` 목록 API에는 더 높은 role이 필요하므로 사용하지 않습니다.
둘 이상이면 임의로 선택하지 않고 `beast_host` 입력을 안내합니다.
현재 v1 `addons` 응답 필드는 deprecated 상태지만 여전히 제공됩니다.
향후 제거되거나 권한/DNS가 다른 설치는 `beast_host` 직접 지정으로 우회할 수 있습니다.
설정 변경·다른 앱 재시작 API는 호출하지 않습니다.

방화벽을 사용하는 경우 새 앱에서 내부 수신기 TCP 30005, DNS, 외부 `aeronexus.kr` TCP 30004로
나갈 수 있어야 합니다. 전송은 원본과 같은 **평문 Beast TCP**이며 TLS가 추가되지는 않습니다.

## 8. 로그 확인과 성공 판정

정상 초기 로그의 핵심은 다음과 같습니다. UUID 값은 로그에 쓰지 않습니다.

```text
Auto-selected Beast source: <실제 내부 DNS 이름>:30005
Beast connected: <실제 내부 DNS 이름>:30005
AeroNexus TCP connected; UUID frame sent (server acceptance is not confirmed)
Stats: input=... eligible=... sent=... offline_or_failed=... bytes=... mlat_dropped=... resync=... source=up upstream=up
```

- `input`: 완성된 Beast 데이터 프레임 수(필터 전, MLAT 포함).
- `eligible`: 필터를 통과한 프레임 수.
- `sent`, `bytes`: 완전히 성공 반환한 데이터 `sendall` 기준. UUID/심장박동 바이트는 제외합니다.
- `offline_or_failed`: 서버 연결이 없거나 쓰기가 실패한 묶음의 프레임 수입니다.
  쓰기 도중 실패한 경우 일부 바이트가 이미 전달됐을 수 있으므로 정밀 손실 계수는 아닙니다.
- `mlat_dropped`: `FF 00 4D 4C 41 54` 타임스탬프 표식 때문에 제외한 프레임 수.
- 통계는 기본 60초 구간마다 초기화됩니다.

TCP 연결 성공, UUID 쓰기 성공, `sent > 0`만으로 **서버가 UUID를 승인하고 자료를 저장했다는 증거는 아닙니다.**
최종 성공은 AeroNexus의 해당 UUID 수신 상태를 확인해야 합니다.
원본 안내상 공개 지도 노출에는 별도 관리자 승인이 필요할 수 있습니다.

연결은 독립적으로 재시도하며 최대 60초까지 간격을 늘립니다. 서버가 읽지 않아서
송신이 막히면 5초 소켓 타임아웃으로 연결을 닫고 재시도합니다.
오프라인 자료는 저장/재전송하지 않으므로 재연결 후에는 실시간 자료부터 전달합니다.
네트워크 문제는 프로세스 내부에서 복구하고, Watchdog은 앱 자체가 비정상 종료됐을 때 복구에 사용합니다.

## 9. 백업과 복원

1. **설정 → 시스템 → 백업**에서 이 앱을 포함한 백업을 만듭니다.
   사용자 설정/UUID와 이 앱의 `/data`가 백업 대상입니다. `backup: hot`으로 실행 중 백업을 허용합니다.
2. 백업 파일을 HA 장비 밖에도 보관합니다. 정기 자동 백업의 포함 앱 설정도 확인하세요.
3. 제공한 **소스 ZIP도 별도로 보관**하세요. 로컬 소스 폴더가 앱 데이터 백업과 함께
   항상 복원된다고 가정하지 않습니다. 필요하면 PC/Samba에서 다시 복사해 재빌드할 수 있어야 합니다.
4. 다른 장비로 옮기면 먼저 기존 ADS-B 피더를 복구한 뒤 이 앱의 설정을 복구합니다.
5. 같은 UUID로 두 장비를 동시에 피딩하지 않도록 이전 장비의 앱을 중지합니다.

이 앱은 자체 로그 파일을 무한히 쌓지 않습니다. 로그는 Supervisor/Docker가 관리하며
장기 로그 보존이나 영구 로그 백업을 별도로 구현한 것은 아닙니다.
진단에 필요한 로그는 앱 Log 탭에서 복사해 별도로 보관하세요.
UUID는 구성 화면과 백업에 저장되므로 공유 전에 값을 지우세요.

## 10. 소스 편집·업데이트·제거

Samba 또는 Terminal의 실제 소스 폴더에서 편집합니다.
예를 들어 `nano /local_apps/aeronexus_feeder/config.yaml`을 사용할 수 있습니다
(`nano`가 없는 터미널이면 Samba에서 PC 편집기를 쓰세요).
파일은 **UTF-8, LF 줄바꿈**으로 저장합니다. ZIP의 셸 파일은 LF로 만들었고,
Dockerfile에서도 실행 권한을 부여합니다.

소스 코드를 수정한 뒤에는:

1. 기존 소스와 앱 설정을 백업합니다.
2. `config.yaml`의 `version`을 예를 들어 `1.0.1`로 올립니다.
3. 앱 스토어에서 업데이트 확인 후 AeroNexus Feeder의 업데이트를 실행합니다.
   로컬 빌드이므로 변경된 Dockerfile/rootfs로 새 이미지가 만들어집니다.
4. 시작/재시작 후 로그를 확인합니다. 단순 재시작은 기존 이미지를 실행합니다.

UUID만 바꾸는 경우에는 소스 편집이나 재빌드가 필요 없습니다. 구성 UI → 저장 → 재시작이면 됩니다.
설치 앱을 제거하면 이 중계기는 중단됩니다. 이후 로컬 소스 폴더가 남아 있으면
백업 보관을 확인한 뒤 PC/Samba에서 지울 수 있습니다. 기존 ADS-B 앱은 별도로 유지됩니다.

## 11. 문제 해결

| 증상 | 확인할 것 |
|---|---|
| 앱이 스토어에 없음 | 실제 `local_apps` 매핑, 폴더 중첩, `config.yaml.txt`, YAML 문법, 업데이트 확인 |
| 여전히 안 보임 | 설정 → 시스템 → 로그에서 Supervisor 선택 후 앱 이름/설정 오류 확인 |
| 빌드 실패 | 인터넷/DNS/저장 공간, ghcr.io·Alpine 저장소 접근, Supervisor 빌드 로그 |
| UUID가 빈 상태로 계속 대기 | 구성 UI 저장 후 재시작했는지 확인 |
| UUID 형식 오류 | 발급값을 36자 그대로 입력; 앞뒤 공백/줄바꿈 제거 |
| 자동 탐색 실패 | 기존 피더의 설치 여부/slug, Supervisor 권한; 필요하면 실제 `beast_host` 지정 |
| 피더를 여러 개 찾음 | 원하는 앱의 내부 DNS 이름을 `beast_host`로 지정 |
| Name resolution 오류 | `_`를 `-`로 치환한 내부 앱 DNS인지, 실제 앱이 설치되어 있는지 확인 |
| Connection refused | 피더 실행 상태, dump1090의 `--net`, 내부 30005 리슨/바인딩 확인 |
| `input=0` 반복 | 포트만 열리고 데이터는 없는지, 기존 지도/SDR 수신, 실제 Beast 형식인지 확인 |
| `eligible=0`이고 input은 증가 | DF17·18 자료가 없는지 확인. 필요 시 일시적으로 `filter: all`로 진단 |
| 서버가 즉시 끊음 | UUID 등록/비활성화/중복 사용을 관리자에게 확인. 정확한 거부 사유는 서버에서 확인 |
| `sent` 증가하지만 지도에 없음 | 서버의 UUID 수신 상태와 지도 공개 승인 확인 |

사용자 장비의 실제 빌드/연결 검증은 `VALIDATION.md`의 마지막 표를 따라 마무리하세요.
