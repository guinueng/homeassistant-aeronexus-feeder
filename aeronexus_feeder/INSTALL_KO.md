# 설치·경로·업데이트 가이드 — 1.1.1

## 권장: 저장소에서 설치

[![Add app repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fguinueng%2Fhomeassistant-aeronexus-feeder)

설정 → 앱 → 앱 설치 → ⋮ → 저장소에 아래 주소를 추가해도 됩니다.

```text
https://github.com/guinueng/homeassistant-aeronexus-feeder
```

저장소가 Public이면 GitHub 로그인/토큰 없이 HA가 내려받을 수 있습니다.
앱 스토어의 AeroNexus Feeder를 설치하고 UUID 입력 → 저장 → 시작하세요.
부팅 시 시작과 Watchdog을 켜세요. 설치 시 공식 HA 이미지/Python을 받기 위한 인터넷 연결이 필요합니다.
지원 CPU는 amd64/aarch64입니다. 버튼은 저장소를 추가하는 화면을 열며 설치를 자동 확정하지 않습니다.

## 외부에서 Terminal만으로 소스 설치

공개 저장소라면 Home Assistant의 Terminal & SSH 웹 터미널에서 실행합니다.

```sh
curl -fsSL https://raw.githubusercontent.com/guinueng/homeassistant-aeronexus-feeder/main/install-local.sh -o /tmp/install-aeronexus-local.sh && bash /tmp/install-aeronexus-local.sh
```

이 설치기는 실행할 때마다 GitHub main의 최신 앱 소스를 내려받습니다.
실제 앱 공유 마운트를 검사하고 기존 소스를 백업한 뒤 배치합니다. 이후 앱 스토어에서
업데이트 확인 → 로컬 앱 설치/업데이트를 마무리하세요. HA 설정 폴더에 Git 저장소를 초기화하지 않습니다.
예전 1.0 소스 내장형 설치 파일은 새 업데이트 관리자를 포함하지 않으므로 다시 사용하지 마세요.

## 경로 구분

| 위치 | 용도 |
|---|---|
| Terminal의 `/local_apps` | 최신 공식 로컬 앱 소스 공유 |
| Terminal의 `/addons` | 구형 addons 매핑의 소스 공유 |
| `~/addons` | 홈에서 보이는 경로. 위 공유와 같은지는 readlink/마운트로 확인 |
| `/homeassistant`, `/config`, `~/config` | Core 설정 폴더. 소스 설치 위치가 아님 |
| Supervisor 내부 `/data/apps/local` | 최신 upstream Supervisor의 소스 경로 |
| `${SUPERVISOR_SHARE}/apps/local` | 최신 upstream의 호스트 경로. 실제 설치 버전/환경에 따라 확인 |
| 앱 내부 `/usr/local/lib/aeronexus` | 이미지에 담긴 HA 실행기/초기 중계 코드 |
| 앱 내부 `/data/options.json` | Supervisor가 쓰는 UUID 등 옵션 |
| 앱 내부 `/data/upstream` | 다운로드한 코드와 정상/이전 버전 상태 |

`~`는 현재 셸의 홈이며 호스트 루트가 아닙니다. 없는 local_apps 폴더를 임의로 만들지 마세요.
현재 경로는 `pwd -P`, 링크는 `readlink -f ~/addons`로 확인할 수 있습니다.
최신 Supervisor는 apps/local, 예전 버전은 addons/local 구조를 사용했습니다.
호스트 절대 경로를 추측해 편집하기보다 실제 앱 공유 매핑으로 접근하세요.

File editor는 파일 업로드/편집에 사용할 수 있지만, local_apps가 매핑되지 않으면
enforce_basepath를 꺼도 로컬 앱 소스에 접근할 수 없습니다. 로컬 소스 배치는 Terminal을 사용하세요.
보호 모드 해제나 호스트 루트 접근은 필요 없습니다.

## 네트워크

새 앱은 host_network:false입니다. 내부 DNS `<기존 앱 ID에서 _를 -로 치환>:30005`를 읽습니다.
기존 피더의 `30005/tcp:null`은 호스트 공개가 꺼진 것이며 내부 서비스가 꺼진 뜻은 아닙니다.
원본 피더의 `SERVICE_ENABLE_DUMP1090:true`와 네트워크 출력이 정상인지 확인하세요.
30004는 기존 피더의 Beast 입력, 30005는 우리가 읽는 Beast 출력입니다.
127.0.0.1은 새 앱 자신이므로 기존 앱 주소로 사용하지 않습니다.

기본 자동 탐색은 GET /supervisor/info의 v1 addons 목록을 사용합니다.
권한은 hassio_api:true와 default role입니다. 이 deprecated 목록이 향후 없어지거나
표준 slug와 다른 설치/복수 피더가 있으면 beast_host를 직접 지정합니다.
GET /addons 목록에 필요한 manager role이나 앱 변경 API는 사용하지 않습니다.

앱은 공식 HTTPS 업데이트 서버와 AeroNexus의 원본 지정 TCP 목적지에 나가는 연결을 만듭니다.
수신 포트를 공개하거나 공유기 포트포워딩을 설정할 필요는 없습니다.
자료 전송은 원본과 같은 평문 Beast TCP입니다.

## 옵션과 로그

기본 UUID만 입력합니다. 선택 옵션 표시 또는 YAML로 편집을 사용하면 다음을 지정할 수 있습니다.

```yaml
uuid: "발급받은 36자 UUID"
beast_host: "f1c878cb-adsb-multi-portal-feeder"
beast_port: 30005
filter: adsb
stats_interval: 60
```

beast_host 예시는 표준 MaxWinterstein 저장소이며 실제 앱 ID에 따라 달라집니다.
주소는 URL/포트 없이, IPv6는 대괄호 없이 입력합니다. 저장 후 재시작해야 반영됩니다.
빈 UUID는 업데이트 확인도 하지 않고 대기합니다.

최초 실행과 새 앱 버전의 첫 실행에만 공식 최신 코드를 확인합니다. 같은 버전 재시작과
실행 중에는 주기적으로 확인하지 않습니다. 1.1.0의 update_interval 값은 무시합니다.
로그에서 공식 다운로드/코드 SHA/적용 또는 유지/복구와 원본 중계기 연결·통계를 확인합니다.
UUID 전체와 앞 8자는 숨기지만 구성 화면/YAML/백업에는 값이 저장됩니다.
TCP 연결과 보내기 성공은 서버의 UUID 승인·자료 저장 증거가 아니므로 AeroNexus에서 최종 확인하세요.
지도 공개 승인은 별도일 수 있습니다. 자동 업데이트의 자세한 한계는 UPDATING.md에 있습니다.

## 백업·이전 설치에서 이동

설정 → 시스템 → 백업에서 이 앱을 포함하면 UUID/옵션 및 정상 코드 캐시가 저장됩니다.
소스 ZIP도 별도 보관하세요. 로그는 Supervisor가 관리하며 무제한 영구 로그 파일은 만들지 않습니다.

로컬 앱에서 GitHub 저장소 앱으로 옮기면 서로 다른 앱 ID로 설치됩니다.
먼저 이전 로컬 앱을 중지한 뒤 새 앱에 UUID를 입력하세요. 같은 UUID로 두 앱을 동시에 피딩하지 마세요.
예전 로컬 1.0을 계속 쓸 경우 최신 소스 설치기 실행 후 1.1.1로 업데이트해야 합니다.
소스 복사나 단순 재시작만으로 이미 빌드된 컨테이너가 바뀌지는 않습니다.

## 문제 해결

| 증상 | 확인 |
|---|---|
| 저장소 추가 실패 | 공개 여부, URL, HA 인터넷/DNS |
| 로컬 앱이 안 보임 | 실제 공유 마운트, 폴더 중첩, YAML, 스토어 업데이트 확인, Supervisor 로그 |
| 설치/빌드 실패 | ghcr.io/Alpine 접근, 공간, 실제 아키텍처, Supervisor 빌드 로그 |
| 공식 업데이트 실패 | HTTPS/DNS/인터넷과 오류 로그. 기존 코드는 유지 |
| 새 원본 검사 거부 | 원본 구조/프로토콜 변경 가능. 어댑터 버전 업데이트 확인 |
| Beast 연결 실패 | 피더 실행, 내부 DNS, 30005 리슨/바인딩 |
| 수신 통계가 0 | 기존 피더의 안테나/SDR/출력/실제 Beast 형식 |
| 서버 즉시 연결 종료 | UUID 등록/비활성화/중복 사용을 관리자에게 확인 |

검증 범위와 아직 실측하지 않은 항목은 VALIDATION.md에 구분했습니다.
