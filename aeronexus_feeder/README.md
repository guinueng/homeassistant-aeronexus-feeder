# AeroNexus Feeder 1.1.2

Home Assistant OS에서 기존 ADS-B Multi-Portal Feeder의 Beast 30005 출력을 AeroNexus로 전달합니다.
`amd64`, `aarch64`를 지원하고 기본 구성 화면에는 UUID만 표시합니다.

[![Add app repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fguinueng%2Fhomeassistant-aeronexus-feeder)

저장소 추가 → 앱 설치 → UUID 입력 → 저장 → 시작 순서입니다.
[TUI 로직 개략도](ARCHITECTURE.md), [설치 가이드](INSTALL_KO.md), [자동 업데이트](UPDATING.md), [검증 결과](VALIDATION.md)를 참조하세요.

## 앱 버전과 관계없이 최신 중계기 받기

1. 이 앱의 구성에서 **사용하지 않는 선택 옵션 표시**를 켭니다.
2. **다음 시작 시 최신 중계기 받기**를 켜고 저장합니다.
3. 앱을 재시작합니다.

공식 AeroNexus 최신 코드를 확인하고 검증 후 적용합니다. 새 HA 앱 버전 배포나
Terminal/File editor 작업은 필요 없습니다. 성공하면 요청 옵션을 자동으로 끕니다.
실패하면 현재 코드로 실행하고 옵션을 켜 둬서 다음 재시작 때 재시도할 수 있습니다.
옵션 자동 해제에 실패했다는 로그가 나오면 구성에서 직접 꺼 주세요.
주기 확인은 활성화하지 않습니다.

## 설치·업데이트 시 최신 코드 확인

최초 실행과 새 앱 버전의 첫 실행에만 공식 feed.sh를 확인합니다. 같은 앱 버전으로
재시작하거나 실행 중일 때는 확인하지 않습니다. 변경된 Python 중계기 전체를 추출하고
호환성 검사 후 자동 적용합니다. 실패하면 마지막 정상 코드 또는 이미지의 초기 코드로 동작합니다.
원본 shell/systemd 설치기는 실행하지 않습니다.

| 파일 | 역할 |
|---|---|
| `config.yaml` | 앱, options/schema, 부팅/백업 |
| `Dockerfile` | HA base 3.24 + Python + 일반 사용자 |
| `rootfs/.../manager.py` | HA 설정·탐색·작업 프로세스·업데이트/복구 |
| `rootfs/.../upstream.py` | 공식 다운로드·추출·검증·버전 캐시 |
| `rootfs/.../engine_runner.py` | 일반 사용자 검사/실행 |
| `rootfs/.../bundled_relay.py` | 네트워크 장애 시 초기 원본 중계기 |
| `rootfs/.../relay.py`, `beast.py` | 설정/탐색 함수와 1.0 전송기 회귀 검사 |
| `translations/` | 한국어/영어 UI |
| `tests/` | 전송 및 자동 업데이트/복구 검사 |

`host_network: false`로 내부 30005를 읽습니다. 호스트 포트 공개나 SDR 접근은 필요 없습니다.
Supervisor API는 default role의 탐색 정보 읽기와 자기 앱의 갱신 요청 옵션 해제에 사용합니다.

```sh
python3 -B -m unittest discover -s tests -v
```
