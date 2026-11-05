# AeroNexus Feeder 사용법

> **비공식 앱 (Unofficial)**: AeroNexus 운영자가 제공하는 공식 Home Assistant 앱이 아닙니다.

공식 안내: [AeroNexus 공식 사이트](https://aeronexus.kr/landing.html) · [공식 피딩 방법](https://aeronexus.kr/landing.html#join)

[![GitHub Repository](https://img.shields.io/badge/GitHub-Repository-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/guinueng/homeassistant-aeronexus-feeder)

[GitHub 저장소 열기](https://github.com/guinueng/homeassistant-aeronexus-feeder) — 소스 코드·설치 파일·변경 사항을 확인할 수 있습니다.

기존 ADS-B Multi-Portal Feeder를 실행하고, 이 앱의 구성에서 UUID 입력 → 저장 → 시작하세요.
빈 UUID는 네트워크 연결 없이 대기합니다. 구성 변경은 재시작해야 적용됩니다.
부팅 시 시작과 Watchdog을 켜세요.

## 중계기 다운로드 출처 — 1.1.5

실행할 공식 중계기는 **`https://aeronexus.kr/feed.sh`에서 직접 받습니다**.
UUID 입력 후 최초 실행, 새 HA 앱 버전으로 업데이트한 뒤 첫 실행, 또는 수동 갱신 요청 때
설치 파일 전체를 새로 다운로드하고 기존 파일의 SHA-256과 비교합니다.
변경된 Python 중계기 전체를 검사한 뒤 실행·적용하며, 설치 스크립트만 바뀌고 중계기가 같으면 재시작하지 않습니다.
같은 앱 버전의 일반 재시작은 이전에 공식 서버에서 받은 정상 캐시를 사용합니다.

GitHub 동봉 중계기 실행 경로는 제거했습니다. 최초 공식 다운로드가 실패하고 정상 캐시도 없으면 중계를 시작하지 않습니다.
GitHub의 `tests/fixtures/` 원본은 검사용 표본이며 설치 이미지에 포함되지 않습니다.
공식 중계기 갱신은 설정의 **다음 시작 시 최신 중계기 받기**를 켜고 저장·재시작하면 됩니다.

## UUID 하나는 기기 하나에서만 사용하세요

같은 UUID로 두 곳에서 접속하면 서버가 **나중에 접속한 쪽을 끊습니다**.
라즈베리파이에서 HA로 옮길 때는 이전 파이의 AeroNexus 피더를 먼저 제거한 뒤 이 앱을 시작하세요.
기존 설치 명령 끝에 `--uninstall`을 붙이면 됩니다.
[이전 절차](https://github.com/guinueng/homeassistant-aeronexus-feeder/blob/main/aeronexus_feeder/INSTALL_KO.md#uuid를-다른-기기로-이전할-때)와 [공식 피더 FAQ](https://aeronexus.kr/feeder-faq.html)를 참조하세요.

서버가 연결 직후 끊으면 **「UUID가 다른 곳에서 사용 중일 수 있습니다」**를 경고로 남기고 **이 중계기를 종료하며 자동 재접속을 중단합니다**.
HA에도 자기 앱의 중지를 요청합니다. 이전 기기의 피더 제거 등 원인을 해결한 뒤 앱을 다시 시작하세요.
중복 사용 확정은 아니므로 UUID 등록/활성화 상태와 네트워크도 함께 확인하세요.

기존 설치 명령의 `--uninstall`은 **이전 라즈베리파이에서** 실행하세요.

## 작동 개략도

```text
앱 시작 -> /init -> run -> manager.py -> 설정·저장된 버전 읽기
  |
  +-- UUID 없음 -> 네트워크 없이 대기
  |
  +-- UUID 있음
       |
       +-- 최초 / 새 앱 버전 / 수동 갱신 요청
       |    -> 공식 Python 다운로드·검사 -> 새 후보 또는 기존 코드
       |
       +-- 같은 버전 일반 재시작 -> 저장된 코드 사용

선택된 중계기의 자료 흐름:
기존 피더 -- Beast TCP 30005 --> 중계기 -- TCP 30004 --> AeroNexus
```

새 후보는 30초간 프로세스가 유지되는지 확인한 후 적용하며 조기 종료하면 이전 코드로 복구합니다.
실행 중 정기 업데이트 확인은 없습니다.
[설치·시작·수동 갱신·복구·네트워크 전체 개략도](https://github.com/guinueng/homeassistant-aeronexus-feeder/blob/main/aeronexus_feeder/ARCHITECTURE.md)를 참조하세요.

## 앱 버전과 관계없이 최신 중계기 받기

1. 이 앱의 구성에서 **사용하지 않는 선택 옵션 표시**를 켭니다.
2. **다음 시작 시 최신 중계기 받기**를 켜고 저장합니다.
3. 앱을 재시작합니다.

공식 AeroNexus 최신 코드를 확인하고 검증 후 적용합니다. 새 HA 앱 버전 배포나
Terminal/File editor 작업은 필요 없습니다. 성공하면 요청 옵션을 자동으로 끕니다.
실패하면 이전에 공식 서버에서 받은 정상 코드가 있을 때만 유지합니다. 옵션은 켜 둬 다음 재시작 때 재시도할 수 있습니다.
옵션 자동 해제에 실패했다는 로그가 나오면 구성에서 직접 꺼 주세요.
주기 확인은 활성화하지 않습니다.

## 최초 설치·앱 업데이트 시 최신 중계기 확인

최초 실행과 새 앱 버전의 첫 실행에만 `https://aeronexus.kr/feed.sh`를 확인합니다.
성공 결과를 영구 저장하므로 같은 버전의 일반 재시작이나 실행 중에는 다시 확인하지 않습니다.
원본의 Python 중계기 전체를 추출하여 UUID·DF17/18·MLAT·Beast escape 검사 후 자동 교체합니다.
30초간 종료되지 않으면 활성 버전으로 저장합니다. 실패 시 기존 코드 유지 또는 이전 버전 복구를 수행합니다.
로그의 `code=<SHA-256 앞 12자>`가 실행 중인 코드 버전입니다.
원본 shell/systemd 설치기는 실행하지 않습니다.

확인에 실패하면 정상 공식 캐시가 있을 때만 유지합니다. 캐시가 없으면 중계를 시작하지 않고 다음 앱 재시작 때 재시도합니다.
새 원본이 인터페이스/프로토콜 검사와 호환되지 않으면 오류 로그와 함께 기존 버전을 유지합니다.
그 경우 HA 앱 어댑터의 업데이트가 필요할 수 있습니다. 교체 때 중계 연결은 잠깐 재연결됩니다.
30초 검사는 서버의 UUID 승인이나 자료 저장을 보장하지 않습니다.

## 선택 설정

사용하지 않는 선택 옵션 표시 또는 YAML로 편집에서 다음을 지정할 수 있습니다.

| 옵션 | 기본 동작 |
|---|---|
| `beast_host` | 기존 피더 자동 탐색 |
| `beast_port` | 30005 |
| `filter` | adsb: DF17/18, MLAT 표식 제외 |
| `stats_interval` | 60초 |
| `refresh_upstream` | 끔. 켜고 저장·재시작하면 한 번 수동 갱신 |
| `update_interval` | 1.1.0 호환용. 값은 무시하며 주기 확인하지 않음 |

127.0.0.1은 이 앱 자신입니다. 다른 앱에는 내부 DNS 이름을 사용하세요.
표준 설치 예시는 `f1c878cb-adsb-multi-portal-feeder`이며 실제 저장소에 따라 다릅니다.
직접 주소를 지정하면 탐색 API는 호출하지 않습니다.

## 로그/백업

공식 업데이트 확인, 코드 SHA, Beast/AeroNexus 연결 및 원본 중계기 통계가 로그에 표시됩니다.
UUID 전체와 앞 8자는 이 앱의 로그 전달 과정에서 숨깁니다.
서버 수신 상태는 AeroNexus에서 최종 확인하세요.

설정 → 시스템 → 백업에 이 앱을 포함하면 옵션/UUID와 `/data/upstream` 캐시가 포함됩니다.
HA 앱 자체의 새 버전은 HA의 업데이트 기능으로 적용합니다.
로컬 앱에서 저장소 앱으로 옮기면 별도 앱이므로 이전 앱을 중지한 뒤 새 앱에 UUID를 입력하세요.
