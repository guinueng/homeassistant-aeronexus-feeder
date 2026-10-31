# 확인한 공식 문서와 소스

확인일: 2026-10-31 (Asia/Seoul).
Home Assistant 공식 문서와 upstream 소스를 조회했습니다. 사용자의 실제 Home Assistant 화면을
원격으로 조작하거나 버전을 조회한 것은 아닙니다. `main`/`dev` 링크는 현재 upstream이며
사용자가 설치한 정식 버전보다 앞설 수 있습니다.

| 출처 | 확인한 내용 |
|---|---|
| [Home Assistant: Apps and integrations](https://www.home-assistant.io/docs/apps-and-integrations/) | 현재 앱 설치 메뉴, HAOS 대상 |
| [Your first app](https://contributors.home-assistant.io/apps/first-app/) | `local_apps` 소스 폴더, 스토어 갱신, 로컬 빌드 |
| [App configuration](https://contributors.home-assistant.io/apps/reference/configuration/) | options/schema, boot, init, host_network, backup, 아키텍처 |
| [Build the container image](https://contributors.home-assistant.io/apps/guides/dockerfile/) | 공식 base `3.24`, 직접 FROM, 현행 멀티아키텍처 구조, build.yaml 비권장 |
| [Run services with S6 overlay](https://contributors.home-assistant.io/apps/guides/s6-overlay/) | longrun, base 의존성, user bundle, finish, with-contenv |
| [Add options](https://contributors.home-assistant.io/apps/guides/options/) | `/data/options.json`, `?` 선택 옵션, 저장 후 재시작, 번역 |
| [Runtime environment](https://contributors.home-assistant.io/apps/reference/environment/) | 앱별 `/data`, 내부 DNS, 브리지 네트워크, 매핑 경로 |
| [Secure your app](https://contributors.home-assistant.io/apps/guides/security/) | default role의 info 읽기, 보호 모드, AppArmor |
| [Supervisor API: Supervisor endpoints](https://contributors.home-assistant.io/apps/supervisor-api/supervisor/) | v1 `/supervisor/info`의 deprecated `addons` 필드 |
| [Supervisor API security.py](https://github.com/home-assistant/supervisor/blob/main/supervisor/api/middleware/security.py) | default role의 `/.+/info` 허용, `/addons`와 권한 차이 |
| [Supervisor API supervisor.py](https://github.com/home-assistant/supervisor/blob/main/supervisor/api/supervisor.py) | `info_v1` 설치 앱 slug 목록 제공 |
| [Supervisor config.py](https://github.com/home-assistant/supervisor/blob/main/supervisor/config.py) | `apps/local`, `apps/data`, `SUPERVISOR_SHARE` 기준 호스트 경로 |
| [Supervisor apps/validate.py](https://github.com/home-assistant/supervisor/blob/main/supervisor/apps/validate.py) | 설정 키/검증 구조 대조. Supervisor 전체 실행 검증은 아님 |
| [Frontend supervisor-app-config.ts](https://github.com/home-assistant/frontend/blob/dev/src/panels/config/apps/app-view/config/supervisor-app-config.ts) | 선택 옵션 숨김 스위치, YAML 편집, 저장 시 옵션 검증/재시작 안내 |
| [공식 Terminal & SSH config](https://github.com/home-assistant/addons/blob/master/ssh/config.yaml) | `local_apps:rw` 매핑 |
| [공식 File editor config](https://github.com/home-assistant/addons/blob/master/configurator/config.yaml) | enforce_basepath와 마운트 구분, local_apps 미매핑 |
| [공식 Samba share config](https://github.com/home-assistant/addons/blob/master/samba/config.yaml) | local_apps 매핑과 enabled_shares |
| [기존 피더 config.yaml](https://github.com/MaxWinterstein/homeassistant-addons/blob/main/adsb-multi-portal-feeder/config.yaml) | 확인 당시 2.8.0.1, Beast 출력 30005와 입력 30004, 호스트 매핑 null |
| [기존 피더 README](https://github.com/MaxWinterstein/homeassistant-addons/blob/main/adsb-multi-portal-feeder/README.md) | 표준 저장소 내부 호스트명 `f1c878cb-adsb-multi-portal-feeder` 예시 |
| [upstream dump1090 run](https://github.com/Thom-x/docker-fr24feed-piaware-dump1090/blob/master/root/etc/s6-overlay/s6-rc.d/dump1090/run) | dump1090 실행 시 `--net`, 사용자가 추가 인자로 바꿀 수 있음 |

AeroNexus 프로토콜 출처는 사용자가 업로드한 스크립트입니다.
별도 서버 인증 규격이나 서버 수신 확인 API를 추정해 추가하지 않았습니다.
원본과 SHA-256은 `NOTICE.md`를 참조하세요.
