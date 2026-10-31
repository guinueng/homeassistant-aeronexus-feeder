# AeroNexus Feeder 1.1.0

Home Assistant OS에서 기존 ADS-B Multi-Portal Feeder의 Beast 30005 출력을 AeroNexus로 전달합니다.
`amd64`, `aarch64`를 지원하고 기본 구성 화면에는 UUID만 표시합니다.

[![Add app repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fguinueng%2Fhomeassistant-aeronexus-feeder)

저장소 추가 → 앱 설치 → UUID 입력 → 저장 → 시작 순서입니다.
[설치 가이드](INSTALL_KO.md), [자동 업데이트](UPDATING.md), [검증 결과](VALIDATION.md)를 참조하세요.

## 자동 업데이트

시작 시와 기본 1시간마다 공식 feed.sh를 확인합니다. 변경된 Python 중계기 전체를 추출하고
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
Supervisor API는 `hassio_api: true`, `hassio_role: default`의 정보 읽기만 사용합니다.

```sh
python3 -B -m unittest discover -s tests -v
```
