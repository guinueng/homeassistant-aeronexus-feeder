# AeroNexus Feeder — Home Assistant 로컬 앱

제공된 `feed.sh`의 Python Beast 중계기를 Home Assistant OS 앱으로 구성한 소스입니다.
기존 **ADS-B Multi-Portal Feeder**가 수신한 자료를 AeroNexus로 전달합니다.

- 기본 설정 화면에는 **AeroNexus UUID** 한 항목이 표시됩니다.
- UUID 없이 먼저 설치할 수 있습니다. 빈 UUID로 실행하면 네트워크 연결 없이 대기합니다.
- UUID 입력 → 저장 → 재시작하면 기존 피더의 내부 Beast 출력 `30005`를 자동 탐색합니다.
- 부팅 시 자동 시작, 연결 끊김 재시도, Supervisor 로그, 60초 통계, 앱 설정 백업을 지원합니다.
- `aarch64`, `amd64`용 소스입니다. 설치 시 HAOS에서 이미지를 빌드합니다.

**먼저 [한국어 설치 가이드](INSTALL_KO.md)를 읽으세요.**

소스 폴더의 설치 위치는 최신 Terminal & SSH에서
`/local_apps/aeronexus_feeder/config.yaml`이 되도록 합니다.
이 폴더 자체를 `local_apps` 아래로 복사하면 됩니다.
오래된 앱에서 같은 공유 폴더를 `/addons`로 보이는 경우는 가이드에 구분했습니다.

| 파일 | 역할 |
|---|---|
| `config.yaml` | 앱 정보, 부팅/백업, options/schema |
| `Dockerfile` | 공식 HA base 3.24 + Python 3 |
| `rootfs/` | S6 서비스와 Beast 중계기 |
| `translations/` | 한국어·영어 설정 UI |
| `DOCS.md` | 앱의 Documentation 탭 안내 |
| `INSTALL_KO.md` | 설치·경로·네트워크·편집·백업·문제 해결 |
| `VALIDATION.md` | 수행한 검증, 한계, 현장 확인 절차 |
| `SOURCES.md` | 2026-10-31 확인한 공식 문서/소스 |
| `NOTICE.md`, `upstream/` | 업로드 원본 출처와 중계기 원문 |
| `tests/` | 외부 계정 없이 실행하는 회귀 검사 |

설계: `host_network: false`, 수신 포트 공개 없음, USB/SDR 사용 없음.
자동 탐색용 Supervisor 권한은 `hassio_api: true`, `hassio_role: default`입니다.
호출하는 API는 읽기 전용 `GET /supervisor/info` 한 종류입니다.

검사 실행(개발용 Python 3.10 이상):

```sh
python3 -B -m unittest discover -s tests -v
```

배포 전 확인 범위: 로컬 모의 TCP 서버를 포함한 회귀 검사는 통과했습니다.
실제 HAOS 빌드·설치와 AeroNexus 계정 수신은 이 작업 환경에서 확인하지 않았습니다.
자세한 결과는 `VALIDATION.md`에 있습니다.
