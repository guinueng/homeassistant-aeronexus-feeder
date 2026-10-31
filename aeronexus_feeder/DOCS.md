# AeroNexus Feeder 사용법

기존 ADS-B Multi-Portal Feeder의 Beast 30005 출력을 AeroNexus로 전달합니다.
UUID는 AeroNexus 관리자에게 발급받으세요.

## 시작

1. 기존 ADS-B Multi-Portal Feeder가 정상 수신 중인지 확인합니다.
2. 이 앱의 **구성(Configuration)** 탭에 AeroNexus UUID를 입력합니다.
3. **저장(Save)** 후 **재시작(Restart)**합니다.
4. **정보(Info)**에서 **부팅 시 시작(Start on boot)**과 **Watchdog**을 켭니다.
5. **로그(Log)**에서 `Beast connected`, `UUID frame sent`, 통계의 `sent`를 확인합니다.
6. AeroNexus 관리자/수신 현황에서 해당 UUID로 자료가 들어오는지 확인합니다.

UUID가 비어 있으면 앱은 연결 없이 대기합니다. UUID는 8-4-4-4-12 형식의 36자입니다.
저장 후 재시작해야 바뀐 값이 적용됩니다.

## 선택 설정

기본 구성에서는 UUID만 입력합니다. 주소를 바꿔야 할 때만 구성 화면의
**사용하지 않는 선택 옵션 표시(Show unused optional configuration options)**를 켜세요.
표시 문구는 Frontend 버전/언어에 따라 약간 다를 수 있습니다.

| 옵션 | 생략 시 동작 |
|---|---|
| `beast_host` | 설치된 ADS-B Multi-Portal Feeder 자동 선택 |
| `beast_port` | 30005 |
| `filter` | `adsb`: DF17·18만 전송, MLAT 표식 제외 |
| `stats_interval` | 60초마다 통계 |

자동 탐색 대상이 여러 개이거나 표준 slug를 사용하지 않으면 `beast_host`를 지정하세요.
직접 지정하면 Supervisor 자동 탐색 API를 호출하지 않습니다.
주소는 포트/URL 없이 입력하고, IPv6는 대괄호 없이 입력합니다.

`127.0.0.1`은 이 앱 자신입니다. 기존 피더의 주소로 사용하지 마세요.
표준 MaxWinterstein 저장소 설치의 예는 `f1c878cb-adsb-multi-portal-feeder`입니다.
저장소/설치 방식이 다르면 실제 앱 ID를 확인해야 합니다.

기본 연결은 앱 간 내부 연결입니다. 기존 피더의 네트워크 설정에서 호스트 30005를
공개할 필요가 없습니다. 이 앱에도 포트 매핑을 추가하지 마세요.

## 로그·자동 복구

- Beast/AeroNexus 접속 실패 시 2→4→8→16→32→60초 간격으로 재시도합니다.
- 60초 이상 유지된 연결이 끊어지면 다시 2초부터 시도합니다.
- 기본 필터는 DF17·18만 전달합니다. `all`에서도 MLAT 표식 프레임은 제외합니다.
- `sent`는 중계기의 TCP 쓰기 완료 기준이며 서버 수신 확인 응답은 아닙니다.
- 데이터가 없어도 AeroNexus 연결에는 30초 유휴 후 심장박동을 보냅니다.
- UUID는 이 앱 로그에 출력하지 않습니다. 구성 화면/YAML 및 백업에는 값이 저장됩니다.

## 백업·업데이트

설정 → 시스템 → 백업에서 이 앱을 포함하세요. UUID를 포함한 앱 설정은 Supervisor가
관리합니다. 소스 폴더/ZIP도 별도 보관하세요. 소스 편집만으로 실행 중 컨테이너는 바뀌지 않습니다.
소스를 고친 뒤 버전을 올리고 앱 스토어 업데이트 확인 → 앱 업데이트를 수행합니다.

상세 설치·경로·복구 안내는 함께 제공된 `INSTALL_KO.md`, 검증 범위는 `VALIDATION.md`를 참조하세요.
