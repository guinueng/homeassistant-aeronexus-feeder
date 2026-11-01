# AeroNexus Feeder for Home Assistant

> **비공식 앱 (Unofficial)**: AeroNexus 운영자가 제공하는 공식 Home Assistant 앱이 아닙니다.

공식 안내: [AeroNexus 공식 사이트](https://aeronexus.kr/landing.html) · [공식 피딩 방법](https://aeronexus.kr/landing.html#join)

기존 ADS-B Multi-Portal Feeder의 Beast 30005 출력을 AeroNexus로 전달하는 Home Assistant OS 앱입니다.
기본 설정 화면에서는 **AeroNexus UUID**만 입력합니다.

[![Add app repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fguinueng%2Fhomeassistant-aeronexus-feeder)
[![GitHub Repository](https://img.shields.io/badge/GitHub-Repository-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/guinueng/homeassistant-aeronexus-feeder)

## UUID 하나는 기기 하나에서만 사용하세요

같은 UUID로 두 곳에서 접속하면 서버가 **나중에 접속한 쪽을 끊습니다**.
라즈베리파이에서 HA로 옮길 때는 이전 파이의 AeroNexus 피더를 먼저 제거한 뒤 이 앱을 시작하세요.
기존 설치 명령 끝에 `--uninstall`을 붙이면 됩니다.
[이전 절차](aeronexus_feeder/INSTALL_KO.md#uuid를-다른-기기로-이전할-때)와 [공식 피더 FAQ](https://aeronexus.kr/feeder-faq.html)를 참조하세요.

서버가 연결 직후 끊으면 로그에 **「UUID가 다른 곳에서 사용 중일 수 있습니다」**를 경고로 표시합니다.
중복 사용 확정은 아니므로 UUID 등록/활성화 상태와 네트워크도 함께 확인하세요.

## 한눈에 보는 작동 방식

```text
GitHub 저장소 -> HA 설치/업데이트 -> 앱 이미지 빌드

앱 시작: /init -> run -> manager.py
  |
  +-- UUID 없음 -> 네트워크 없이 대기
  |
  +-- UUID 있음 -> 설정과 저장된 버전 확인
       |
       +-- 최초 / 새 앱 버전 / 수동 갱신 요청
       |    -> 공식 Python 다운로드·검사
       |    -> 새 후보 선택 / 실패하면 기존 코드 유지
       |
       +-- 같은 버전의 일반 재시작
            -> 저장된 코드 사용

선택된 중계기의 자료 흐름:
기존 ADS-B 피더 -- Beast TCP 30005 --> 중계기 -- TCP 30004 --> AeroNexus
```

새 Python 코드는 30초 실행 검사를 거쳐 적용하고, 조기 종료하면 이전 코드로 복구합니다.
일반 재시작에서는 저장된 코드를 사용하며 실행 중 정기 업데이트 확인은 없습니다.
설치·수동 갱신·복구·컨테이너 경로와 네트워크는 [TUI 로직 개략도](aeronexus_feeder/ARCHITECTURE.md)에서 자세히 볼 수 있습니다.

## 앱 버전과 관계없이 최신 중계기 받기

1. 이 앱의 구성에서 **사용하지 않는 선택 옵션 표시**를 켭니다.
2. **다음 시작 시 최신 중계기 받기**를 켜고 저장합니다.
3. 앱을 재시작합니다.

공식 AeroNexus 최신 코드를 확인하고 검증 후 적용합니다. 새 HA 앱 버전 배포나
Terminal/File editor 작업은 필요 없습니다. 성공하면 요청 옵션을 자동으로 끕니다.
실패하면 현재 코드로 실행하고 옵션을 켜 둬서 다음 재시작 때 재시도할 수 있습니다.
옵션 자동 해제에 실패했다는 로그가 나오면 구성에서 직접 꺼 주세요.
주기 확인은 활성화하지 않습니다.

## 설치

1. 위 버튼으로 저장소를 추가합니다.
2. 설정 → 앱 → 앱 설치에서 AeroNexus Feeder를 설치합니다.
3. 구성 → UUID 입력 → 저장 → 시작합니다.
4. 부팅 시 시작과 Watchdog을 켭니다.
5. 로그와 AeroNexus 수신 화면에서 실제 자료가 들어오는지 확인합니다.

버튼이 등록 창을 열지 않으면 앱 스토어의 ⋮ → 저장소에 다음 주소를 직접 추가하세요.

```text
https://github.com/guinueng/homeassistant-aeronexus-feeder
```

버튼은 저장소 등록 화면을 엽니다. 앱 설치와 UUID 입력은 사용자 화면에서 마무리합니다.

## 설치·업데이트 시 최신 중계기 확인 — 1.1.3

- **최초 실행과 새로운 앱 버전으로 업데이트한 뒤 첫 실행에만** 공식 `https://aeronexus.kr/feed.sh`를 확인합니다.
- 확인 결과를 영구 저장하므로 같은 앱 버전의 재시작과 실행 중에는 다시 확인하지 않습니다.
- 변경되면 원본의 **Python 중계기 전체**를 내려받아 문법·UUID·Beast·DF17/18·MLAT 검사를 수행합니다.
- 통과한 코드를 일반 사용자 프로세스로 실행하고, 30초간 종료되지 않으면 정상 버전으로 저장합니다.
- 다운로드/검사 실패 시 기존 버전을 유지하고, 초기 실행 실패 시 이전 버전으로 복구합니다.
- UUID와 Beast 주소/필터/통계 간격은 앱 설정에서 자동 전달합니다.
- 원본에 일관된 릴리스 번호가 없어 SHA-256을 코드 버전으로 기록합니다.
- 마지막 정상 버전은 `/data/upstream`에 보관하고 앱 백업에 포함합니다.

1시간 주기 확인은 제거했습니다. 최초 확인이 실패하면 기존 코드로 실행하고 다음 앱 재시작 시 한 번 재시도합니다.
원본 shell/systemd 설치기는 실행하지 않습니다. 새 원본이 기존 인터페이스/프로토콜 검사와
호환되지 않으면 기존 버전을 유지하고 로그를 남깁니다. 이 경우 HA 어댑터 업데이트가 필요할 수 있습니다.
UUID가 비어 있으면 업데이트 확인을 포함한 네트워크 연결 없이 대기합니다.

**설치한 앱 버전마다 한 번 받는 공식 Python 중계기**와 **HA 앱 자체 업데이트**는 별도입니다.
업데이터/설정 UI/Dockerfile 변경은 앱 버전을 올려 배포하고 HA의 앱 업데이트로 적용합니다.
현재는 HAOS에서 Dockerfile을 빌드하는 배포 방식으로, GHCR 사전 빌드 이미지가 필요하지 않습니다.

## Terminal로 소스 설치

공개 저장소인 경우 Home Assistant의 Terminal & SSH 안에서 다음을 실행할 수 있습니다.

```sh
curl -fsSL https://raw.githubusercontent.com/guinueng/homeassistant-aeronexus-feeder/main/install-local.sh -o /tmp/install-aeronexus-local.sh && bash /tmp/install-aeronexus-local.sh
```

설치기는 GitHub의 최신 앱 소스를 받아 실제 `/local_apps`, `/addons`, `~/addons` 공유를 확인하고
배치합니다. 기존 소스는 먼저 백업합니다. 이후 HA에서 앱 설치/업데이트를 완료하세요.
예전에 배포한 소스 내장형 1.0 설치 파일은 고정본이므로 1.1.1 이상으로 이동해야 합니다.

## 안내

- [TUI 로직 작동 개략도](aeronexus_feeder/ARCHITECTURE.md)
- [한국어 설치·경로·업데이트 가이드](aeronexus_feeder/INSTALL_KO.md)
- [자동 업데이트와 복구](aeronexus_feeder/UPDATING.md)
- [검증 결과](aeronexus_feeder/VALIDATION.md)
- [공식 자료](aeronexus_feeder/SOURCES.md)
- [원본 출처와 배포 허락](aeronexus_feeder/NOTICE.md)

이 저장소는 AeroNexus 운영자가 발행한 공식 Home Assistant 앱이라는 의미가 아닙니다.
원본 코드의 배포 허락은 저장소 소유자가 받았다고 확인했습니다. 원본에 별도 라이선스를 임의로 부여하지 않습니다.
